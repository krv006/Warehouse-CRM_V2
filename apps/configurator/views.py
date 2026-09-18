from django.db.transaction import atomic
from django.http import HttpResponse
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST

from apps.accounts.permissions import (
    ConfigurationRequestAccess,
    ConfiguratorAccess,
    IsOwnerOrAdmin,
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
    act_suggestion_text,
    approve_configuration,
    assemble_configuration,
    build_configuration_workbook,
    change_quantity,
    notify_engineers_about_request,
    reject_configuration,
    request_prices,
    send_missing_to_procurement,
    submit_configuration,
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

    permission_classes = [ConfiguratorAccess, IsOwnerOrAdmin]

    queryset = (
        Configuration.objects
        .select_related('client', 'base_product', 'act', 'warehouse', 'created_by')
        .prefetch_related('items__component__stocks', 'replenishments')
        .all()
    )
    serializer_class = ConfigurationSerializer
    search_fields = ['number', 'client__full_name', 'client__company_name']
    filterset_fields = ['status', 'client', 'base_product', 'act', 'created_by']
    ordering_fields = ['created_at', 'number', 'created_by']

    def get_queryset(self):
        """EGALIK §3.2: engineer o'zinikini, sales o'z zayavkasidan tug'ilganini.

        Sales uchun bog'lanish zanjir bo'ylab: Configuration -> requests ->
        created_by — aks holda u o'z shartnomasining ortidagi
        konfiguratsiyani umuman ko'rmay qolardi.
        """
        qs = super().get_queryset()
        user = self.request.user
        if user.is_admin:
            return qs
        if user.is_engineer:
            return qs.filter(created_by=user)
        if user.is_sales:
            return qs.filter(requests__created_by=user).distinct()
        return qs.none()

    # §11.1: finalize engineerda (ConfiguratorAccess); #4: texnik tasdiq
    # (approve/reject) esa sales bosqichi
    def get_permissions(self):
        if self.action in ('approve', 'reject'):
            from apps.accounts.permissions import IsAdminOrSales

            return [IsAdminOrSales()]
        return super().get_permissions()

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

    def submit(self, request, pk=None):
        """POST /configurations/{id}/submit/ — texnik yechim sales ko'rigiga (#4)."""
        configuration = submit_configuration(self.get_object(), request.user)
        self.log_action(
            ActivityLog.Action.UPDATE, configuration,
            'Texnik yechim sales ko\'rigiga yuborildi',
        )
        return Response(self.get_serializer(configuration).data)

    def approve(self, request, pk=None):
        """POST /configurations/{id}/approve/ — sales texnik yechimni tasdiqlaydi."""
        configuration = approve_configuration(
            self.get_object(), request.user, request.data.get('comment', ''),
        )
        self.log_action(
            ActivityLog.Action.APPROVE, configuration, 'Texnik yechim tasdiqlandi',
        )
        return Response(self.get_serializer(configuration).data)

    def reject(self, request, pk=None):
        """POST /configurations/{id}/reject/ — sales izoh bilan qaytaradi."""
        configuration = reject_configuration(
            self.get_object(), request.user, request.data.get('comment', ''),
        )
        self.log_action(
            ActivityLog.Action.REJECT, configuration, request.data.get('comment', ''),
        )
        return Response(self.get_serializer(configuration).data)

    def request_prices(self, request, pk=None):
        """POST /configurations/{id}/request-prices/ — narx so'rovi (YANGI-OQIM B2).

        TLD emas: buyurtmachi shunchaki tannarxni mahsulot kartasida kiritadi.
        Takrorida eski eslatma yangilanadi. Narx kelgach sales xabar oladi.
        """
        products = request_prices(self.get_object(), request.user)
        self.log_action(
            ActivityLog.Action.UPDATE, self.get_object(),
            f"Narx so'raldi: {', '.join(products)}",
        )
        return Response({'requested': products})

    def change_quantity(self, request, pk=None):
        """POST /configurations/{id}/change-quantity/ — partiya soni (4-to'plam §2).

        Mijoz sonni o'zgartirsa zanjir qaytadan boshlanmaydi: bron yangi
        partiyaga moslashadi, zayavka soni ergashadi, `approved` yechim
        sales ko'rigiga qaytadi. Tana: {"quantity": 100, "comment": "..."}.
        """
        configuration = change_quantity(
            self.get_object(), request.user,
            quantity=request.data.get('quantity'),
            comment=str(request.data.get('comment', '') or ''),
        )
        self.log_action(
            ActivityLog.Action.UPDATE, configuration,
            f'Partiya {configuration.quantity} taga o\'zgartirildi'
            + (f": {request.data.get('comment')}" if request.data.get('comment') else ''),
        )
        return Response(self.get_serializer(configuration).data)

    def assemble(self, request, pk=None):
        """POST /configurations/{id}/assemble/ — yig'ish, alohida qadam (#4).

        Faqat sales tasdiqlagan (`approved`) yechim yig'iladi. build:
        butlovchilar chiqadi, variant kiradi; modify: tayyor mahsulot fizik
        o'zgartiriladi (tana: {"removals": {...}}). Butlovchi yetmasa 400 —
        mol TLD orqali kelgach qayta bosiladi. Javobda `act_suggestion` —
        ACT uchun bajarilgan ishdan tayyor matn (#4D).
        """
        configuration = self.get_object()
        assembled, missing = assemble_configuration(
            configuration, request.user,
            removals=request.data.get('removals'), strict=True,
        )
        if assembled:
            self.log_action(
                ActivityLog.Action.UPDATE, configuration,
                f"Yig'ildi: {configuration.variant.sku} omborga kirdi",
            )
        data = self.get_serializer(configuration).data
        data['assembled'] = assembled
        data['assembly_missing'] = missing
        data['act_suggestion'] = act_suggestion_text(configuration)
        return Response(data)

    def finalize(self, request, pk=None):
        """POST /configurations/{id}/finalize/ — yakunlash (#4: endi faqat bitta ish).

        Shartlari: texnik yechim **tasdiqlangan**, mahsulot **yig'ilgan**,
        **ACT** biriktirilgan (tanada {"act": id} berish mumkin). Yakunda
        `ready` bo'ladi va **draft shartnoma avtomatik ochiladi** — mahsulot
        haqiqatan tayyor bo'lgandagina. {"client": id} — shartnoma mijozi
        (berilmasa zayavkadagi).
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
        if configuration.status != Configuration.Status.APPROVED:
            return Response(
                {'detail': (
                    'Avval texnik yechim tasdiqlansin: engineer submit -> '
                    'sales approve — shundan keyin yakunlanadi.'
                )},
                status=HTTP_400_BAD_REQUEST,
            )
        if not configuration.assembled_at:
            return Response(
                {'detail': "Avval mahsulot yig'ilsin (assemble) — yakunlash tayyor mahsulot bilan bo'ladi."},
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

        with atomic():
            # Tanadagi mijoz (eski oqim mosligi) — konfiguratsiyada bo'lmasa yoziladi
            if client and not configuration.client_id:
                configuration.client = client
            configuration.status = Configuration.Status.READY
            configuration.save()

            # 4-to'plam §4: "yakunlang" vazifasi bajarildi — engineerniki yopiladi
            from apps.core.services import resolve_notifications

            resolve_notifications('Configuration', configuration.pk, user=request.user)

            # §11.4/B5: konfiguratsiya broni bo'shaydi — endi shartnomaning
            # qattiq broni o'z o'rnini egallaydi (bitta bron ko'chadi)
            from apps.inventory.services import (
                sync_configuration_reservations,
                sync_contract_reservations,
            )

            # YANGI OQIM: shartnoma allaqachon bor (B1, approve'da ochilgan).
            # B6: qatordagi bazaviy model yig'ilgan VARIANTGA ko'chadi — son va
            # narx tegilmaydi (imzolangan pul o'zgarmaydi), faqat SKU aniqlashadi.
            # Aks holda ship bazaviy modelni chiqim qilib omborni buzardi (§3.1).
            contract = configuration.active_contract
            if contract and configuration.variant_id:
                moved = contract.items.filter(
                    product=configuration.base_product,
                ).update(product=configuration.variant)
                if moved:
                    self.log_action(
                        ActivityLog.Action.UPDATE, contract,
                        f'{contract.number} qatori variantga ko\'chdi: '
                        f'{configuration.variant.sku}',
                    )
            # B7: pul allaqachon kelgan bo'lsa zanjir yopildi — sold
            if contract and contract.status in ('active', 'completed'):
                configuration.status = Configuration.Status.SOLD
                configuration.save()

            sync_configuration_reservations(configuration)
            if contract:
                sync_contract_reservations(contract)
        self.log_action(
            ActivityLog.Action.UPDATE, configuration,
            f'Yakunlandi ({configuration.get_mode_display()}), variant: '
            f'{configuration.variant.sku}'
            + (f', shartnoma: {contract.number}' if contract else ''),
        )
        data = self.get_serializer(configuration).data
        data['contract'] = (
            {'id': contract.id, 'number': contract.number, 'status': contract.status}
            if contract else None
        )
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
    permission_classes = [ConfiguratorAccess, IsOwnerOrAdmin]
    filterset_fields = ['configuration', 'component']

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_admin:
            return qs
        if user.is_engineer:
            return qs.filter(configuration__created_by=user)
        if user.is_sales:
            return qs.filter(configuration__requests__created_by=user).distinct()
        return qs.none()

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
        from rest_framework.exceptions import PermissionDenied

        configuration = serializer.validated_data.get('configuration')
        if configuration is None:
            raise ValidationError({'configuration': "Konfiguratsiya ko'rsatilishi shart."})
        # EGALIK §3: boshqa engineerning konfiguratsiyasiga qator qo'shilmaydi
        user = self.request.user
        if not user.is_admin and configuration.created_by_id not in (None, user.id):
            raise PermissionDenied('Bu konfiguratsiya sizniki emas.')
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
    filterset_fields = ['status', 'client', 'taken_by', 'configuration', 'created_by']
    ordering_fields = ['created_at', 'number', 'created_by']

    def get_queryset(self):
        """EGALIK §3.3: engineer `new` hammasini ko'radi (kim birinchi olsa
        o'shaniki) + o'zi olganini; sales — o'zi yozganini; admin — hammasini."""
        from django.db.models import Q

        qs = super().get_queryset()
        user = self.request.user
        if user.is_admin:
            return qs
        if user.is_engineer:
            return qs.filter(
                Q(status=ConfigurationRequest.Status.NEW) | Q(taken_by=user),
            )
        if user.is_sales:
            return qs.filter(created_by=user)
        return qs.none()

    def perform_create(self, serializer):
        super().perform_create(serializer)
        # Yangi zayavka haqida engineerlar darrov xabar oladi
        notify_engineers_about_request(serializer.instance)

    # YANGI-OQIM B16: miqdor faqat ochiq holatlarda o'zgaradi va
    # konfiguratsiya bilan SINXRON — ikki hujjatda ikki xil son qolmasin
    QUANTITY_EDITABLE = (
        ConfigurationRequest.Status.NEW,
        ConfigurationRequest.Status.IN_PROGRESS,
    )

    def perform_update(self, serializer):
        instance = serializer.instance
        new_quantity = serializer.validated_data.get('quantity')
        quantity_changed = (
            new_quantity is not None and new_quantity != instance.quantity
        )
        if quantity_changed and instance.status not in self.QUANTITY_EDITABLE:
            raise ValidationError({
                'quantity': (
                    f"'{instance.get_status_display()}' holatida miqdor "
                    "o'zgartirilmaydi."
                ),
            })
        if quantity_changed and instance.configuration_id:
            # Bitta mantiq (4-to'plam §2): son, bron, shartnoma va holat
            # birga o'zgaradi; to'lov kelgan/TLD yo'lga chiqqan bo'lsa 400
            from apps.configurator.services import change_quantity

            change_quantity(
                instance.configuration, self.request.user,
                quantity=new_quantity,
                comment=f'{instance.number} zayavkasida son o\'zgartirildi',
                via_request=True,
            )
        super().perform_update(serializer)

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

    # `complete` olib tashlandi (#4): engineer endi konfiguratsiyani
    # `submit` bilan sales ko'rigiga yuboradi, zayavka holati esa sales
    # tasdig'ida (`approve`) DONE bo'ladi — tasdiqsiz "tayyor" yo'q.
