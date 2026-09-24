from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST

from apps.accounts.permissions import (
    ConfigurationRequestAccess,
    ConfiguratorAccess,
    IsAdminOrBugalter,
    IsOwnerOrAdmin,
)
from apps.configurator.models import (
    Act,
    Configuration,
    ConfigurationItem,
    ConfigurationRequest,
    ConfigurationRequestLine,
)
from apps.configurator.serializers import (
    ActSerializer,
    ConfigurationSerializer,
    ConfigurationItemSerializer,
    ConfigurationRequestLineSerializer,
    ConfigurationRequestSerializer,
)
from apps.configurator.services import (
    _deal_models_for_request,
    act_suggestion_text,
    add_request_line,
    answer_clarification,
    approve_act,
    approve_configuration,
    ask_sales,
    assemble_configuration,
    build_configuration_workbook,
    cancel_chain,
    change_quantity,
    deal_act_suggestion_text,
    deal_answer,
    deal_approve,
    deal_ask_sales,
    deal_assemble,
    deal_finalize,
    deal_reject,
    deal_request_prices,
    deal_submit,
    delete_request_line,
    detach_configuration,
    log_request_event,
    reject_act,
    reject_request,
    release_request,
    resend_request,
    notify_engineers_about_request,
    reject_configuration,
    request_prices,
    send_missing_to_procurement,
    submit_act_for_review,
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
    filterset_fields = ['is_active', 'status']

    # 20-§3.3: `approve`/`reject` — bugalter (admin); qolgani (create/
    # update/`submit`) — engineer (admin), bugungidek (`ConfiguratorAccess`)
    def get_permissions(self):
        if self.action in ('approve', 'reject'):
            return [IsAdminOrBugalter()]
        return super().get_permissions()

    def submit(self, request, pk=None):
        """POST /acts/{id}/submit/ — engineer bugalter tasdig'iga yuboradi (20-§3.3)."""
        act = submit_act_for_review(
            self.get_object(), request.user, comment=str(request.data.get('comment', '') or ''),
        )
        self.log_action(ActivityLog.Action.UPDATE, act, f'{act.number}: bugalter tasdig\'iga yuborildi')
        return Response(self.get_serializer(act).data)

    def approve(self, request, pk=None):
        """POST /acts/{id}/approve/ — bugalter (admin) tasdiqlaydi (20-§3.3)."""
        act = approve_act(
            self.get_object(), request.user, comment=str(request.data.get('comment', '') or ''),
        )
        self.log_action(ActivityLog.Action.APPROVE, act, f'{act.number}: ACT tasdiqlandi')
        return Response(self.get_serializer(act).data)

    def reject(self, request, pk=None):
        """POST /acts/{id}/reject/ — bugalter (admin) izoh bilan qaytaradi (20-§3.3)."""
        comment = str(request.data.get('comment', '') or '')
        act = reject_act(self.get_object(), request.user, comment)
        self.log_action(ActivityLog.Action.REJECT, act, f'{act.number}: qaytarildi — {comment}')
        return Response(self.get_serializer(act).data)


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
            # 12-§2 (B): qo'shimcha model qatori zayavkaga faqat
            # ConfigurationRequestLine orqali ulangan bo'lishi mumkin —
            # aks holda sales o'z ikkinchi modelini ko'rmay/tasdiqlolmay qolardi
            from django.db.models import Q

            return qs.filter(
                Q(requests__created_by=user)
                | Q(extra_request_lines__request__created_by=user),
            ).distinct()
        return qs.none()

    # §11.1: finalize engineerda (ConfiguratorAccess); #4: texnik tasdiq
    # (approve/reject) sales bosqichi; B12: bekor qilish — sales/admin;
    # 6-to'plam §4: partiya sonini ham SALES belgilaydi (mijoz bilan kelishadi)
    def get_permissions(self):
        if self.action in (
            'approve', 'reject', 'cancel', 'change_quantity', 'answer', 'detach',
        ):
            from apps.accounts.permissions import IsAdminOrSales

            return [IsAdminOrSales()]
        return super().get_permissions()

    def ask_sales(self, request, pk=None):
        """POST /configurations/{id}/ask-sales/ — aniqlashtirish (9-to'plam §1).

        Rad etish EMAS: tarkib ham, bron ham joyida — sales javob bergach
        engineer o'sha yerdan davom etadi.
        """
        configuration = ask_sales(
            self.get_object(), request.user,
            comment=str(request.data.get('comment', '') or ''),
        )
        self.log_action(
            ActivityLog.Action.UPDATE, configuration,
            f"Sales'dan aniqlashtirish so'raldi: {request.data.get('comment')}",
        )
        return Response(self.get_serializer(configuration).data)

    def answer(self, request, pk=None):
        """POST /configurations/{id}/answer/ — sales javobi (9-to'plam §1)."""
        configuration = answer_clarification(
            self.get_object(), request.user,
            comment=str(request.data.get('comment', '') or ''),
        )
        self.log_action(
            ActivityLog.Action.UPDATE, configuration,
            f"Savolga javob berildi: {request.data.get('comment')}",
        )
        return Response(self.get_serializer(configuration).data)

    def cancel(self, request, pk=None):
        """POST /configurations/{id}/cancel/ — butun zanjirni to'xtatish (B12)."""
        configuration = self.get_object()
        result = cancel_chain(
            configuration, request.user,
            reason=str(request.data.get('reason', '') or ''),
        )
        self.log_action(
            ActivityLog.Action.UPDATE, configuration,
            f"Zanjir bekor qilindi: {result['reason']}",
        )
        return Response(result)

    def detach(self, request, pk=None):
        """POST /configurations/{id}/detach/ — modelni savdodan chiqarish (14-§5).

        Butun zanjirni emas — BITTA modelni: mijoz voz kechdi yoki moli
        oylab kelmayapti, savdodagi boshqa model esa tayyor.
        Tana: {"reason": "...", "target": "cancel" | "separate"}.
        """
        configuration = self.get_object()
        result = detach_configuration(
            configuration, request.user,
            reason=str(request.data.get('reason', '') or ''),
            target=str(request.data.get('target', 'cancel') or 'cancel'),
        )
        self.log_action(
            ActivityLog.Action.UPDATE, configuration,
            f"Savdodan chiqarildi ({result['target']}): {result['reason']}",
        )
        return Response(result)

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
        """POST /configurations/{id}/approve/ — sales texnik yechimni tasdiqlaydi.

        12-§2 (C2): tanada `contract` (id) berilsa — yangi shartnoma
        ochilmaydi, mavjud qoralamaga yangi model qatori qo'shiladi
        (bitta savdoda bir nechta model). 14-§3: `contract` berilmasa,
        savdodagi boshqa modelning DRAFT shartnomasi endi AVTOMATIK
        topiladi va shunga qo'shiladi; `separate_contract: true` — mijoz
        buni ataylab alohida shartnoma qilishni so'ragan holat uchun.
        """
        contract = None
        contract_id = request.data.get('contract')
        if contract_id:
            from apps.sales.models import Contract

            contract = get_object_or_404(Contract, pk=contract_id)
        configuration = approve_configuration(
            self.get_object(), request.user, request.data.get('comment', ''),
            contract=contract,
            separate_contract=bool(request.data.get('separate_contract', False)),
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
        from apps.configurator.services import finalize_configuration

        configuration = self.get_object()
        client = None
        if request.data.get('client'):
            client = Client.objects.filter(pk=request.data['client']).first()
            if not client:
                return Response(
                    {'client': 'Mijoz topilmadi.'}, status=HTTP_400_BAD_REQUEST,
                )
        act = None
        if request.data.get('act'):
            act = Act.objects.filter(pk=request.data['act'], is_active=True).first()
            if not act:
                return Response(
                    {'act': 'ACT topilmadi yoki faol emas.'},
                    status=HTTP_400_BAD_REQUEST,
                )

        configuration, contract, variant_moved = finalize_configuration(
            configuration, request.user, act=act, client=client,
        )
        if variant_moved:
            self.log_action(
                ActivityLog.Action.UPDATE, contract,
                f'{contract.number} qatori variantga ko\'chdi: '
                f'{configuration.variant.sku}',
            )
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
            from django.db.models import Q

            return qs.filter(
                Q(configuration__requests__created_by=user)
                | Q(configuration__extra_request_lines__request__created_by=user),
            ).distinct()
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
        .prefetch_related('events__created_by')
        .all()
    )
    serializer_class = ConfigurationRequestSerializer
    permission_classes = [ConfigurationRequestAccess]
    search_fields = ['number', 'text', 'client__full_name', 'client__company_name']
    filterset_fields = ['status', 'client', 'taken_by', 'configuration', 'created_by']
    ordering_fields = ['created_at', 'number', 'created_by']

    def act_suggestion(self, request, pk=None):
        """GET /configuration-requests/{id}/act-suggestion/ — 14-§7 (2).

        Savdo darajasidagi ACT matni: har YIG'ILGAN model uchun bitta
        abzats (hali yig'ilmaganlar kirmaydi). Bitta modelli zayavkada
        javob `assemble` javobidagi bitta modellik matn bilan bir xil.
        """
        request_obj = self.get_object()
        return Response({'act_suggestion': deal_act_suggestion_text(request_obj)})

    # ----------------------------------------------------- 16-§A: savdo amallari
    #
    # A0: qaror savdoniki (bitta bosish), mehnat modelniki (yig'ish —
    # atomar emas). Model darajasidagi manzillar (`/configurations/{id}/...`)
    # o'chirilmaydi — bitta modelli zayavkada yagona yo'l, ko'p modelli
    # savdoda ham qoladi (admin bitta modelni qo'lda surishi kerak bo'lganda).

    def submit(self, request, pk=None):
        """POST /configuration-requests/{id}/submit/ — savdo darajasida ko'rikka (16-§A2)."""
        request_obj = self.get_object()
        configurations = deal_submit(request_obj, request.user)
        self.log_action(
            ActivityLog.Action.UPDATE, request_obj,
            f"{request_obj.number}: {len(configurations)} ta model ko'rikka yuborildi",
        )
        return Response(self.get_serializer(request_obj).data)

    def approve(self, request, pk=None):
        """POST /configuration-requests/{id}/approve/ — savdo darajasida tasdiq (16-§A2)."""
        request_obj = self.get_object()
        configurations = deal_approve(request_obj, request.user, request.data.get('comment', ''))
        self.log_action(
            ActivityLog.Action.APPROVE, request_obj,
            f"{request_obj.number}: {len(configurations)} ta model tasdiqlandi",
        )
        return Response(self.get_serializer(request_obj).data)

    def reject(self, request, pk=None):
        """POST /configuration-requests/{id}/reject/ — ikki bosqich, bitta manzil.

        B15: zayavka hali ISHGA OLINMAGAN (`new`) — engineer matnni
        tushunmadi, sales'ga qaytaradi. 16-§A2: modellar sales ko'rigida
        (`pending_sales`) bo'lsa — bu ENDI texnik yechimni sales savdo
        darajasida qaytarishi. Boshqa har qanday holatda (masalan, ishga
        olingan-u hali ko'rikka yuborilmagan) — eski xabar: "ask-sales"
        yoki "release" ishlatilsin (`reject_request` o'zi shu qoidani biladi).
        """
        comment = str(request.data.get('comment', '') or '')
        request_obj = self.get_object()
        has_pending_sales = any(
            cfg.status == Configuration.Status.PENDING_SALES
            for cfg in _deal_models_for_request(request_obj)
        )
        if not has_pending_sales:
            request_obj = reject_request(request_obj, request.user, comment)
            self.log_action(
                ActivityLog.Action.REJECT, request_obj,
                f"Sales'ga qaytarildi: {comment}",
            )
            request_obj.refresh_from_db()
            return Response(self.get_serializer(request_obj).data)

        configurations = deal_reject(request_obj, request.user, comment)
        self.log_action(
            ActivityLog.Action.REJECT, request_obj,
            f"{request_obj.number}: {len(configurations)} ta model qaytarildi — {comment}",
        )
        return Response(self.get_serializer(request_obj).data)

    def ask_sales(self, request, pk=None):
        """POST /configuration-requests/{id}/ask-sales/ — savdo darajasida savol (16-§A3)."""
        comment = str(request.data.get('comment', '') or '')
        request_obj = self.get_object()
        deal_ask_sales(request_obj, request.user, comment)
        self.log_action(
            ActivityLog.Action.UPDATE, request_obj,
            f"{request_obj.number}: sales'dan aniqlashtirish so'raldi — {comment}",
        )
        return Response(self.get_serializer(request_obj).data)

    def answer(self, request, pk=None):
        """POST /configuration-requests/{id}/answer/ — savdo darajasida javob (16-§A3)."""
        comment = str(request.data.get('comment', '') or '')
        request_obj = self.get_object()
        deal_answer(request_obj, request.user, comment)
        self.log_action(
            ActivityLog.Action.UPDATE, request_obj,
            f'{request_obj.number}: savolga javob berildi — {comment}',
        )
        return Response(self.get_serializer(request_obj).data)

    def request_prices(self, request, pk=None):
        """POST /configuration-requests/{id}/request-prices/ — savdo darajasida narx so'rovi (16-§A2)."""
        request_obj = self.get_object()
        requested = deal_request_prices(request_obj, request.user)
        self.log_action(
            ActivityLog.Action.UPDATE, request_obj,
            f"{request_obj.number}: narx so'raldi — "
            f"{', '.join(row['name'] for row in requested)}",
        )
        return Response({'requested': requested})

    def assemble(self, request, pk=None):
        """POST /configuration-requests/{id}/assemble/ — savdo darajasida yig'ish (16-§A2).

        A0: mehnat modelniki — atomar emas, natija model-model qaytadi.
        """
        request_obj = self.get_object()
        result = deal_assemble(request_obj, request.user)
        self.log_action(
            ActivityLog.Action.UPDATE, request_obj,
            f"{request_obj.number}: yig'ildi — {', '.join(result['assembled'])}",
        )
        return Response(result)

    def finalize(self, request, pk=None):
        """POST /configuration-requests/{id}/finalize/ — savdo darajasida yakunlash (16-§A2)."""
        from apps.clients.models import Client

        client = None
        if request.data.get('client'):
            client = Client.objects.filter(pk=request.data['client']).first()
            if not client:
                return Response({'client': 'Mijoz topilmadi.'}, status=HTTP_400_BAD_REQUEST)
        act = None
        if request.data.get('act'):
            act = Act.objects.filter(pk=request.data['act'], is_active=True).first()
            if not act:
                return Response({'act': 'ACT topilmadi yoki faol emas.'}, status=HTTP_400_BAD_REQUEST)

        request_obj = self.get_object()
        result = deal_finalize(request_obj, request.user, act=act, client=client)
        contract = result['contract']
        self.log_action(
            ActivityLog.Action.UPDATE, request_obj,
            f"{request_obj.number}: yakunlandi — {', '.join(result['finalized'])}",
        )
        return Response({
            'finalized': result['finalized'],
            'pending': result['pending'],
            'contract': (
                {'id': contract.id, 'number': contract.number, 'status': contract.status}
                if contract else None
            ),
        })

    def lines(self, request, pk=None):
        """POST /configuration-requests/{id}/lines/ — savdoga model/tovar qo'shish (16-§B2).

        Savdo boshlangandan keyin mijoz fikridan qaytsa yoki qo'shimcha
        narsa so'rasa — shu orqali. "Almashtirish" alohida amal emas:
        shu + `detach` (16-§B4). Tana: {"kind": "model"|"item",
        "base_product": id, "quantity": N, "text": "...", "mode": "build"}.
        """
        from apps.inventory.models import Product

        base_product = Product.objects.filter(pk=request.data.get('base_product')).first()
        line, configuration = add_request_line(
            self.get_object(), request.user,
            kind=request.data.get('kind', ConfigurationRequestLine.Kind.MODEL),
            base_product=base_product,
            quantity=request.data.get('quantity', 1),
            text=str(request.data.get('text', '') or ''),
            mode=request.data.get('mode'),
        )
        self.log_action(
            ActivityLog.Action.CREATE, line.request,
            f'{line.request.number}: yangi qator qo\'shildi — {line.base_product.name}',
        )
        return Response({
            'line': ConfigurationRequestLineSerializer(line).data,
            'configuration': (
                {'id': configuration.id, 'number': configuration.number}
                if configuration else None
            ),
        }, status=201)

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
        # B15: tarix birinchi qadamdan boshlanadi
        from apps.configurator.models import ConfigurationRequestEvent

        log_request_event(
            serializer.instance, ConfigurationRequestEvent.Stage.CREATED,
            self.request.user, (serializer.instance.text or '')[:200],
        )

    # YANGI-OQIM B16 + 6-to'plam §4: miqdor ochiq holatlarda o'zgaradi va
    # konfiguratsiya bilan SINXRON. `done` ham ochiq: chegara to'lovda,
    # zayavka holatida emas — `change_quantity` ichida to'lov/TLD/yig'ish
    # shartlari baribir tekshiriladi, `approved` esa sales ko'rigiga qaytadi
    QUANTITY_EDITABLE = (
        ConfigurationRequest.Status.NEW,
        ConfigurationRequest.Status.IN_PROGRESS,
        ConfigurationRequest.Status.DONE,
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
        — berilmasa zayavkadagi qiymatlar olinadi. 12-§2 (B2): bitta amalda
        qo'shimcha MODEL qatorlariga ham chernovik ochiladi; har biriga
        alohida rejim — {"line_modes": {"<line_id>": "build|modify"}}.
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
        line_modes = request.data.get('line_modes') or {}
        for line_mode in line_modes.values():
            if line_mode not in Configuration.Mode.values:
                raise ValidationError({
                    'line_modes': f"Noto'g'ri rejim: {line_mode}. Ruxsat: build, modify.",
                })

        request_obj = take_request(
            self.get_object(), request.user,
            base_product=base_product, warehouse=warehouse, mode=mode,
            line_modes=line_modes,
        )
        self.log_action(
            ActivityLog.Action.UPDATE, request_obj,
            f'Engineer ishga oldi — {request_obj.configuration.number} ochildi',
        )
        return Response(self.get_serializer(request_obj).data)

    def release(self, request, pk=None):
        """POST /configuration-requests/{id}/release/ — hovuzga qaytarish (9-§2).

        Muammo engineerda (vaqti yo'q) — zayavka `new` ga qaytadi, boshqa
        engineer oladi; ochilgan konfiguratsiya bekor bo'lib broni bo'shaydi.
        """
        request_obj = release_request(
            self.get_object(), request.user,
            comment=str(request.data.get('comment', '') or ''),
        )
        self.log_action(
            ActivityLog.Action.UPDATE, request_obj,
            f"Hovuzga qaytarildi: {request.data.get('comment')}",
        )
        request_obj.refresh_from_db()
        return Response(self.get_serializer(request_obj).data)

    def resend(self, request, pk=None):
        """POST /configuration-requests/{id}/resend/ — sales tuzatib qayta yuboradi."""
        request_obj = resend_request(self.get_object(), request.user)
        self.log_action(
            ActivityLog.Action.UPDATE, request_obj, 'Qayta yuborildi — hovuzga qaytdi',
        )
        request_obj.refresh_from_db()
        return Response(self.get_serializer(request_obj).data)

    def cancel(self, request, pk=None):
        """POST /configuration-requests/{id}/cancel/ — zanjirni to'xtatish (B17).

        Eng ko'p ishlatiladigan kirish nuqtasi: sales zayavkani bekor qiladi —
        shartnoma hali ochilmagan payt (§2.1 aylanmasi ichida).
        """
        request_obj = self.get_object()
        result = cancel_chain(
            request_obj, request.user,
            reason=str(request.data.get('reason', '') or ''),
        )
        self.log_action(
            ActivityLog.Action.UPDATE, request_obj,
            f"Zanjir bekor qilindi: {result['reason']}",
        )
        return Response(result)

    # `complete` olib tashlandi (#4): engineer endi konfiguratsiyani
    # `submit` bilan sales ko'rigiga yuboradi, zayavka holati esa sales
    # tasdig'ida (`approve`) DONE bo'ladi — tasdiqsiz "tayyor" yo'q.


class ConfigurationRequestLineViewSet(BaseModelViewSet):
    """Zayavka qatorlari — faqat TOVAR qatorini olib tashlash uchun (16-§B5 f).

    Model turidagi qator (`kind=model`) konfiguratsiyasi bor — u
    `configurations/{id}/detach/` orqali chiqadi (14-§5); bu yerda faqat
    `DELETE` ochiq va faqat konfiguratorsiz TOVAR qatorlariga ishlaydi.
    """

    queryset = ConfigurationRequestLine.objects.select_related(
        'request', 'base_product', 'configuration', 'contract_item',
    ).all()
    serializer_class = ConfigurationRequestLineSerializer
    permission_classes = [ConfigurationRequestAccess]
    http_method_names = ['get', 'delete', 'head', 'options']

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_admin:
            return qs
        if user.is_sales:
            return qs.filter(request__created_by=user)
        return qs.none()

    def perform_destroy(self, instance):
        delete_request_line(instance, self.request.user)
        super().perform_destroy(instance)
