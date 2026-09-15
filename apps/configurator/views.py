from django.db.transaction import atomic
from django.http import HttpResponse
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST

from apps.accounts.permissions import (
    ConfigurationRequestAccess,
    ConfiguratorAccess,
)
from apps.configurator.models import (
    Act,
    Configuration,
    ConfigurationItem,
    ConfigurationRequest,
)
from apps.configurator.serializers import (
    ActSerializer,
    ConfigurationSerializer,
    ConfigurationItemSerializer,
    ConfigurationRequestSerializer,
)
from apps.configurator.services import (
    assemble_variant,
    build_configuration_workbook,
    complete_request,
    finalize_modification,
    notify_engineers_about_request,
    resolve_variant,
    send_missing_to_procurement,
    take_request,
)
from apps.core.mixins import BaseModelViewSet
from apps.core.models import ActivityLog

XLSX_CONTENT_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


class ActViewSet(BaseModelViewSet):
    """ACT hujjatlari — engineer kiritadi (admin ham mumkin) — §11.1.

    ACT tarkibni o'zgartirishga asos bo'ladigan texnik hujjat, uni tarkibni
    o'zgartiradigan odam — engineer yuritadi. U ACT ni biriktirib finalize
    qiladi va tayyor natijani salesga topshiradi.
    """

    queryset = Act.objects.select_related('created_by').all()
    serializer_class = ActSerializer
    permission_classes = [ConfiguratorAccess]
    search_fields = ['number', 'title']
    filterset_fields = ['is_active']


class ConfigurationViewSet(BaseModelViewSet):
    """Configurator: hamma ko'radi, yozish ishlari Engineerda.

    Sales matnli zayavka yuboradi (ConfigurationRequest), Engineer shu yerda
    konfiguratsiyani tayyorlab zayavkaga biriktiradi.
    """

    permission_classes = [ConfiguratorAccess]

    queryset = (
        Configuration.objects
        .select_related('client', 'base_product', 'act', 'warehouse', 'created_by')
        .prefetch_related('items__component__stocks', 'replenishments')
        .all()
    )
    serializer_class = ConfigurationSerializer
    search_fields = ['number', 'client__full_name', 'client__company_name']
    filterset_fields = ['status', 'client', 'base_product', 'act']
    ordering_fields = ['created_at', 'number']

    # §11.1: finalize ham engineerda — ACT bilan yakunlash tarkib egasining
    # ishi. ConfiguratorAccess (yozish: engineer, admin) buni o'zi qamraydi.

    def _check_draft(self, configuration):
        """Yakunlangan konfiguratsiya o'zgartirilmaydi — faqat chernovik (TZ 6.4)."""
        if configuration.status != Configuration.Status.DRAFT:
            raise ValidationError({
                'detail': (
                    f"'{configuration.get_status_display()}' holatidagi "
                    "konfiguratsiyani o'zgartirib bo'lmaydi — faqat chernovik."
                ),
            })

    def perform_update(self, serializer):
        self._check_draft(serializer.instance)
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        self._check_draft(instance)
        super().perform_destroy(instance)

    def stock_check(self, request, pk=None):
        """GET /configurations/{id}/stock-check/ — qaysi butlovchi omborda bor."""
        configuration = self.get_object()
        variant = configuration.variant or configuration.matching_variant
        return Response({
            'configuration': configuration.number,
            'ready_variant': variant.sku if variant else None,
            'variant_price': variant.stock_price if variant else None,
            'variant_stock': variant.total_stock if variant else None,
            'total_price': configuration.total_price,
            'items': [
                {
                    'component': item.component.name,
                    'quantity': item.quantity,
                    'available': item.available,
                    'shortage': item.shortage,
                    'source': item.source,
                    'unit_price': item.unit_price,
                    'needs_price': item.needs_price,
                }
                for item in configuration.items.select_related('component')
            ],
        })

    def changes(self, request, pk=None):
        """GET /configurations/{id}/changes/ — zavod tarkibiga nisbatan farq.

        Qo'shilganlar (ombordan olinadi) va yechib olinganlar (omborga
        qaytadi, narxi o'zgartirilishi mumkin).
        """
        configuration = self.get_object()
        changes = configuration.changes
        return Response({
            'configuration': configuration.number,
            'mode': configuration.mode,
            'added': [
                {
                    'component': row['component'].id,
                    'name': row['component'].name,
                    'quantity': row['quantity'],
                    'available': row['component'].total_stock,
                }
                for row in changes['added']
            ],
            'removed': [
                {
                    'component': row['component'].id,
                    'name': row['component'].name,
                    'quantity': row['quantity'],
                    'unit_price': row['unit_price'],
                }
                for row in changes['removed']
            ],
        })

    def finalize(self, request, pk=None):
        """POST /configurations/{id}/finalize/ — ACT bilan yakunlash (§11.1: engineer).

        Engineer ACT ni biriktirib yakunlaydi va natijani salesga topshiradi
        ("Yakunlash va salesga topshirish" — UI da bitta tugma).

        Tana (ixtiyoriy): {"act": id} — ACT shu yerning o'zida biriktiriladi,
        oldindan PATCH qilish shart emas; {"client": id} — shartnoma uchun mijoz
        (berilmasa zayavkadagi mijoz olinadi).

        Yakunda avtomatik **draft shartnoma** ochiladi (mijoz aniq bo'lsa):
        qatori — tayyor variant, narxi konfiguratsiyadan, QQS bilan. Javobda
        `contract` maydoni keladi. Build rejimida yig'ish ham shu yerda (§10.1).
        """
        from apps.clients.models import Client

        configuration = self.get_object()
        client = None
        if request.data.get('client'):
            client = Client.objects.filter(pk=request.data['client']).first()
            if not client:
                return Response(
                    {'client': 'Mijoz topilmadi.'}, status=HTTP_400_BAD_REQUEST,
                )
        if configuration.status != Configuration.Status.DRAFT:
            return Response(
                {'detail': 'Faqat chernovik holatidagi konfiguratsiya yakunlanadi.'},
                status=HTTP_400_BAD_REQUEST,
            )
        if request.data.get('act'):
            act = Act.objects.filter(pk=request.data['act'], is_active=True).first()
            if not act:
                return Response(
                    {'act': 'ACT topilmadi yoki faol emas.'},
                    status=HTTP_400_BAD_REQUEST,
                )
            configuration.act = act
        if not configuration.act:
            return Response(
                {'detail': 'Yakunlash uchun ACT biriktirilishi shart.'},
                status=HTTP_400_BAD_REQUEST,
            )
        if not configuration.items.exists():
            return Response(
                {'detail': 'Konfiguratsiya qatorlari kiritilmagan.'},
                status=HTTP_400_BAD_REQUEST,
            )

        # TZ 6.2: narxi aniqlanmagan butlovchi bo'lsa, jarayon yakunlanmaydi
        no_price = configuration.items_without_price
        if no_price:
            return Response(
                {
                    'detail': 'Narxi kiritilmagan butlovchilar bor.',
                    'items': [item.component.name for item in no_price],
                },
                status=HTTP_400_BAD_REQUEST,
            )

        # Bitta tranzaksiya: variant yaratish, ombor harakatlari va statusning
        # o'zgarishi yo to'liq bajariladi, yo umuman yo'q (yarim holat qolmaydi)
        with atomic():
            if configuration.mode == Configuration.Mode.MODIFY:
                # Tayyor mahsulot fizik o'zgartiriladi: ombor harakatlari + bugalterga xabar
                variant, created = finalize_modification(
                    configuration, request.user, request.data.get('removals'),
                )
                assembled, assembly_missing = True, []
            else:
                variant, created = resolve_variant(configuration)
                configuration.variant = variant
                # §10.1: jismoniy yig'ish — butlovchilar chiqadi, variant kiradi.
                # Yetishmasa bloklanmaydi: mol TLD orqali kelgach /assemble/ yoki
                # to'lov paytida avtomatik yig'iladi.
                assembled, assembly_missing = assemble_variant(
                    configuration, request.user, strict=False,
                )

            configuration.variant = variant
            configuration.status = Configuration.Status.READY
            configuration.save()

            # §11.4: chernovik emas — yumshoq bron bo'shaydi; shartnoma ochilsa
            # uning qattiq broni o'z o'rnini egallaydi (bitta bron ko'chadi)
            from apps.inventory.services import sync_configuration_reservations

            sync_configuration_reservations(configuration)

            # Bugalterga yuborishdan oldin shartnoma tayyor tursin (chop etish shakli bilan)
            from apps.sales.services import create_contract_from_configuration

            contract = create_contract_from_configuration(
                configuration, request.user, client,
            )
        self.log_action(
            ActivityLog.Action.UPDATE, configuration,
            f'Yakunlandi ({configuration.get_mode_display()}), variant: {variant.sku} '
            + ('(yangi)' if created else '(ombordan)')
            + (f', shartnoma: {contract.number}' if contract else ''),
        )
        if contract:
            self.log_action(
                ActivityLog.Action.CREATE, contract,
                f'{configuration.number} dan avtomatik ochildi',
            )
        data = self.get_serializer(configuration).data
        data['contract'] = (
            {'id': contract.id, 'number': contract.number, 'status': contract.status}
            if contract else None
        )
        # Front ko'rsatadi: yig'ildimi yoki qaysi butlovchilar kutilmoqda
        data['assembled'] = assembled
        data['assembly_missing'] = assembly_missing
        return Response(data)

    def assemble(self, request, pk=None):
        """POST /configurations/{id}/assemble/ — variantni jismoniy yig'ish (§10.1).

        Finalize paytida butlovchi yetmagan bo'lsa, mol kelgach shu tugma
        bosiladi: butlovchilar ombordan chiqadi, variant omborga kiradi.
        """
        from apps.configurator.services import assemble_variant

        configuration = self.get_object()
        assembled, _ = assemble_variant(configuration, request.user, strict=True)
        if assembled:
            self.log_action(
                ActivityLog.Action.UPDATE, configuration,
                f"Yig'ildi: {configuration.variant.sku} omborga kirdi",
            )
        data = self.get_serializer(configuration).data
        data['assembled'] = assembled
        return Response(data)

    def request_procurement(self, request, pk=None):
        """POST /configurations/{id}/request-procurement/ — yetishmayotganlar buyurtmachiga.

        Omborda yo'q butlovchilardan to'ldirish hisobi (TLD-) ochiladi;
        buyurtmachi, sales va bugalterga xabar tushadi. Keyin TZ 7 zanjiri:
        buyurtmachi submit -> bugalter -> admin -> to'lov -> kirim (timeline).
        """
        from apps.procurement.serializers import ReplenishmentSerializer

        replenishment = send_missing_to_procurement(self.get_object(), request.user)
        self.log_action(
            ActivityLog.Action.CREATE, replenishment,
            f"Configuratordan: yetishmayotganlar buyurtmachiga yuborildi",
        )
        return Response(
            ReplenishmentSerializer(replenishment).data, status=201,
        )

    def export_excel(self, request, pk=None):
        """GET /configurations/{id}/export-excel/ — chernovik Excel."""
        configuration = self.get_object()
        workbook = build_configuration_workbook(configuration)
        response = HttpResponse(content_type=XLSX_CONTENT_TYPE)
        response['Content-Disposition'] = f'attachment; filename="{configuration.number}.xlsx"'
        workbook.save(response)
        return response


class ConfigurationItemViewSet(BaseModelViewSet):
    """Konfiguratsiya qatorlari. Faqat chernovik holatida o'zgartiriladi."""

    queryset = ConfigurationItem.objects.select_related('configuration', 'component').all()
    serializer_class = ConfigurationItemSerializer
    permission_classes = [ConfiguratorAccess]
    filterset_fields = ['configuration', 'component']

    def _check_draft(self, configuration):
        if configuration.status != Configuration.Status.DRAFT:
            raise ValidationError({
                'detail': "Yakunlangan konfiguratsiya qatorlari o'zgartirilmaydi.",
            })

    def _resync_reservations(self, configuration):
        """§11.4: qator o'zgardi — yumshoq bron qatorlarga moslashadi."""
        from apps.inventory.services import sync_configuration_reservations

        sync_configuration_reservations(configuration)

    def perform_create(self, serializer):
        configuration = serializer.validated_data.get('configuration')
        if configuration is None:
            raise ValidationError({'configuration': "Konfiguratsiya ko'rsatilishi shart."})
        self._check_draft(configuration)
        super().perform_create(serializer)
        self._resync_reservations(configuration)

    def perform_update(self, serializer):
        self._check_draft(serializer.instance.configuration)
        super().perform_update(serializer)
        self._resync_reservations(serializer.instance.configuration)

    def perform_destroy(self, instance):
        configuration = instance.configuration
        self._check_draft(configuration)
        super().perform_destroy(instance)
        self._resync_reservations(configuration)


class ConfigurationRequestViewSet(BaseModelViewSet):
    """Zayavkalar: sales yozadi va Engineerga yuboradi, Engineer bajaradi."""

    queryset = (
        ConfigurationRequest.objects
        .select_related('client', 'configuration', 'taken_by', 'created_by')
        .all()
    )
    serializer_class = ConfigurationRequestSerializer
    permission_classes = [ConfigurationRequestAccess]
    search_fields = ['number', 'text', 'client__full_name', 'client__company_name']
    filterset_fields = ['status', 'client', 'taken_by', 'configuration']
    ordering_fields = ['created_at', 'number']

    def perform_create(self, serializer):
        super().perform_create(serializer)
        # Yangi zayavka haqida engineerlar darrov xabar oladi
        notify_engineers_about_request(serializer.instance)

    def take(self, request, pk=None):
        """POST /configuration-requests/{id}/take/ — Engineer ishga oladi.

        Chernovik konfiguratsiya avtomatik ochiladi va zavod tarkibi yuklanadi.
        Tana (ixtiyoriy): {"base_product": id, "warehouse": id, "mode": "build|modify"}
        — berilmasa zayavkadagi qiymatlar olinadi.
        """
        from apps.inventory.models import Product, Warehouse

        base_product = Product.objects.filter(
            pk=request.data.get('base_product'),
        ).first()
        warehouse = Warehouse.objects.filter(
            pk=request.data.get('warehouse'),
        ).first()
        mode = request.data.get('mode')
        if mode and mode not in Configuration.Mode.values:
            raise ValidationError({'mode': f"Noto'g'ri rejim: {mode}. Ruxsat: build, modify."})

        request_obj = take_request(
            self.get_object(), request.user,
            base_product=base_product, warehouse=warehouse, mode=mode,
        )
        self.log_action(
            ActivityLog.Action.UPDATE, request_obj,
            f'Engineer ishga oldi — {request_obj.configuration.number} ochildi',
        )
        return Response(self.get_serializer(request_obj).data)

    def complete(self, request, pk=None):
        """POST /configuration-requests/{id}/complete/ — konfiguratsiya biriktiriladi."""
        configuration = Configuration.objects.filter(
            pk=request.data.get('configuration'),
        ).first()
        request_obj = complete_request(self.get_object(), request.user, configuration)
        self.log_action(
            ActivityLog.Action.UPDATE, request_obj,
            f'Konfiguratsiya tayyor: {configuration.number}',
        )
        return Response(self.get_serializer(request_obj).data)
