from rest_framework.response import Response

from apps.accounts.permissions import IsAdminOrBugalter, IsAdminOrSales, IsOwnerOrAdmin
from apps.core.mixins import BaseModelViewSet
from apps.core.models import ActivityLog
from apps.sales.models import (
    Contract,
    ContractItem,
    ContractApproval,
    ContractPayment,
    Lead,
)
from apps.sales.serializers import (
    ContractSerializer,
    ContractItemSerializer,
    ContractApprovalSerializer,
    ContractPaymentSerializer,
    LeadSerializer,
)
from apps.sales.services import (
    approve_contract,
    confirm_payment,
    reject_contract,
    send_contract_missing_to_procurement,
    ship_contract,
    submit_contract,
)

# Bu amallarni bugalter (va admin) bajaradi, sales emas
BUGALTER_ACTIONS = {'approve', 'reject', 'confirm_payment'}
# #2: yetkazishni mol bilan ishlaydigan odam bosadi — buyurtmachi/bugalter
SHIP_ACTIONS = {'ship'}


class ContractViewSet(BaseModelViewSet):
    """Shartnoma: sales tuzadi, bugalter va admin tasdiqlaydi, bugalter pulni yopadi."""

    queryset = (
        Contract.objects
        .select_related('client', 'configuration', 'created_by')
        .prefetch_related('items__product', 'payments', 'approvals__decided_by')
        .all()
    )
    serializer_class = ContractSerializer
    permission_classes = [IsAdminOrSales, IsOwnerOrAdmin]
    search_fields = ['number', 'client__full_name', 'client__company_name']
    # EGALIK §5: admin/bugalter "sales1 ning shartnomalari"ni ajratib ko'radi
    filterset_fields = ['status', 'client', 'currency', 'configuration', 'created_by']
    ordering_fields = ['created_at', 'number', 'total_amount', 'created_by']

    EDITABLE_STATUSES = {Contract.Status.DRAFT, Contract.Status.REJECTED}

    def get_queryset(self):
        """EGALIK §3.2: sales faqat O'Z shartnomasini ko'radi.

        Bugalter va admin zanjirda — hammasini ko'radi (tasdiqlash uchun).
        Egasiz eski yozuvlar faqat admin/bugalterga ko'rinadi.
        """
        qs = super().get_queryset()
        user = self.request.user
        if user.is_admin or user.is_bugalter:
            return qs
        if user.is_sales:
            return qs.filter(created_by=user)
        if user.is_supplier:
            # #2: buyurtmachi yetkazish navbatini ko'radi — faol, yetkazilmagan
            return qs.filter(
                status=Contract.Status.ACTIVE, delivered_at__isnull=True,
            )
        return qs.none()

    def get_permissions(self):
        if self.action in BUGALTER_ACTIONS:
            return [IsAdminOrBugalter()]
        if self.action in SHIP_ACTIONS:
            from apps.accounts.permissions import ProcurementSharedAccess

            return [ProcurementSharedAccess()]
        return super().get_permissions()

    def _check_editable(self, contract):
        """Tasdiqqa yuborilgan shartnoma o'zgarmaydi (faqat admin) — §11.3 asosi."""
        from rest_framework.exceptions import PermissionDenied

        user = self._current_user()
        if user and user.is_admin:
            return
        if contract.status not in self.EDITABLE_STATUSES:
            raise PermissionDenied(
                'Shartnoma tasdiqqa yuborilgan — endi faqat admin o\'zgartira oladi.',
            )

    def perform_create(self, serializer):
        super().perform_create(serializer)
        # Mijozning ochiq kelishuvi shartnomaga bog'lanadi — quvur yopiladi
        from apps.inventory.services import sync_contract_reservations
        from apps.sales.services import link_lead_to_contract

        link_lead_to_contract(serializer.instance)
        # §11.4: shartnoma tuzilishi bilan mahsulot band qilinadi
        sync_contract_reservations(serializer.instance)

    def perform_update(self, serializer):
        self._check_editable(serializer.instance)
        super().perform_update(serializer)
        from apps.inventory.services import sync_contract_reservations

        sync_contract_reservations(serializer.instance)

    def perform_destroy(self, instance):
        self._check_editable(instance)
        super().perform_destroy(instance)

    def submit(self, request, pk=None):
        """POST /contracts/{id}/submit/ — sales bugalterga yuboradi."""
        contract = submit_contract(self.get_object(), request.user)
        self.log_action(ActivityLog.Action.UPDATE, contract, 'Shartnoma bugalterga yuborildi')
        return Response(self.get_serializer(contract).data)

    def approve(self, request, pk=None):
        """POST /contracts/{id}/approve/ — avval bugalter (Didox qabuli), keyin admin.

        Bugalter bosqichida tanada `didox_number` yuborilsa saqlanadi (§11.2);
        summa chegaradan kichik bo'lsa admin bosqichi o'tkazib yuboriladi (§11.3).
        """
        contract = approve_contract(
            self.get_object(), request.user, request.data.get('comment', ''),
            didox_number=str(request.data.get('didox_number', '') or ''),
        )
        self.log_action(ActivityLog.Action.APPROVE, contract, contract.get_status_display())
        return Response(self.get_serializer(contract).data)

    def reject(self, request, pk=None):
        """POST /contracts/{id}/reject/ — rad etish."""
        contract = reject_contract(
            self.get_object(), request.user, request.data.get('comment', ''),
        )
        self.log_action(ActivityLog.Action.REJECT, contract, request.data.get('comment', ''))
        return Response(self.get_serializer(contract).data)

    def confirm_payment(self, request, pk=None):
        """POST /contracts/{id}/confirm-payment/ — pul keldi, muddat sanog'i boshlanadi."""
        from apps.core.utils import parse_amount

        contract = self.get_object()
        # Satr/float kelsa ham 500 bo'lmaydi — noto'g'ri format 400 qaytaradi
        raw_amount = request.data.get('amount')
        amount = parse_amount(raw_amount, 'amount')
        # §3: summa yuborilmasa — oldindan to'lov; ANIQ 0 yuborilsa esa
        # default olinmaydi, servis uni rad etadi (`amount or ...` nolni
        # "yuborilmagan" deb chalkashtirardi)
        if raw_amount in (None, ''):
            amount = contract.prepayment_amount
        payment = confirm_payment(
            contract,
            request.user,
            amount=amount,
            method=request.data.get('method', ContractPayment.Method.TRANSFER),
        )
        contract.refresh_from_db()
        self.log_action(
            ActivityLog.Action.APPROVE, contract, f"To'lov tasdiqlandi: {payment.amount}",
        )
        return Response(self.get_serializer(contract).data)

    def ship(self, request, pk=None):
        """POST /contracts/{id}/ship/ — yetkazib berish (#2): mol shu yerda chiqadi."""
        contract = ship_contract(self.get_object(), request.user)
        self.log_action(
            ActivityLog.Action.UPDATE, contract,
            f'Yetkazildi: {contract.delivered_at}',
        )
        return Response(self.get_serializer(contract).data)

    def request_procurement(self, request, pk=None):
        """POST /contracts/{id}/request-procurement/ — band qilinmagani buyurtmachiga (#2)."""
        from apps.procurement.serializers import ReplenishmentSerializer

        replenishment = send_contract_missing_to_procurement(
            self.get_object(), request.user,
        )
        self.log_action(
            ActivityLog.Action.CREATE, replenishment,
            'Shartnomadan: yetishmayotganlar buyurtmachiga yuborildi',
        )
        return Response(ReplenishmentSerializer(replenishment).data, status=201)

    def print_form(self, request, pk=None):
        """GET /contracts/{id}/print/ — chop etish shakli uchun barcha ma'lumot.

        Bajaruvchi (kompaniya rekvizitlari), buyurtmachi (mijoz), qatorlar
        (QQS bilan) va yig'indilar bitta javobda — front rasmiy shartnoma
        modalini shu javobdan chizadi. Qator narxlari bor — faqat sales/admin.
        """
        from rest_framework.exceptions import PermissionDenied

        from apps.core.models import CompanyProfile

        user = request.user
        if not (user.is_admin or user.is_sales):
            raise PermissionDenied('Chop etish shakli sales va admin uchun.')

        contract = self.get_object()
        company = CompanyProfile.load()
        client = contract.client
        return Response({
            'number': contract.number,
            'status': contract.status,
            'didox_number': contract.didox_number,
            'signed_at': contract.signed_at,
            'start_date': contract.start_date,
            'term_days': contract.term_days,
            'deadline': contract.progress.get('deadline'),
            'currency': contract.currency,
            'company': {
                'name': company.name,
                'inn': company.inn,
                'phone': company.phone,
                'email': company.email,
                'address': company.address,
                'bank_name': company.bank_name,
                'mfo': company.mfo,
                'account_number': company.account_number,
                'director_name': company.director_name,
            },
            'client': {
                'name': client.display_name,
                'type': client.type,
                'inn': client.inn,
                'jshshir': client.jshshir,
                'phone': client.phone,
                'email': client.email,
                'address': client.address,
                'bank_name': client.bank_name,
                'mfo': client.mfo,
                'account_number': client.account_number,
                'director_name': client.director_name,
            },
            'items': [
                {
                    'name': item.product.name,
                    'sku': item.product.sku,
                    'unit': 'dona',
                    'quantity': item.quantity,
                    'unit_price': item.unit_price,
                    'vat_percent': item.vat_percent,
                    'vat_amount': item.vat_amount,
                    'total_with_vat': item.total_with_vat,
                }
                for item in contract.items.select_related('product')
            ],
            'totals': {
                'items_total': contract.items_total,
                'vat_total': contract.vat_total,
                'total': contract.items_total_with_vat,
                'total_amount': contract.total_amount,
                'prepayment_percent': contract.prepayment_percent,
                'prepayment_amount': contract.prepayment_amount,
            },
            'terms': company.contract_terms,
            'note': contract.note,
        })

    def timeline(self, request, pk=None):
        """GET /contracts/{id}/timeline/ — line chart uchun kunlar va ranglar."""
        contract = self.get_object()
        return Response({
            'number': contract.number,
            'status': contract.status,
            'total_amount': contract.total_amount,
            'paid': contract.paid,
            'balance': contract.balance,
            **contract.progress,
        })

    def deadlines(self, request):
        """GET /contracts/deadlines/ — muddati yaqinlashgan faol shartnomalar."""
        contracts = self.get_queryset().filter(status=Contract.Status.ACTIVE)
        data = [
            {
                'id': contract.id,
                'number': contract.number,
                'client': contract.client.display_name,
                'days_left': contract.days_left,
                'color': contract.color,
                'balance': contract.balance,
            }
            for contract in contracts
        ]
        return Response(sorted(data, key=lambda row: (row['days_left'] is None, row['days_left'])))


class ContractItemViewSet(BaseModelViewSet):
    """Shartnoma qatorlari.

    Tasdiqqa yuborilgan shartnoma qatorlari o'zgarmaydi (faqat admin) —
    aks holda kichik summa bilan tasdiq olib, keyin qatorlarni oshirish
    mumkin bo'lardi. Har o'zgarishda shartnoma summasi qayta hisoblanadi.
    """

    queryset = ContractItem.objects.select_related('contract', 'product').all()
    serializer_class = ContractItemSerializer
    permission_classes = [IsAdminOrSales, IsOwnerOrAdmin]
    filterset_fields = ['contract', 'product']

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_admin or user.is_bugalter:
            return qs
        if user.is_sales:
            return qs.filter(contract__created_by=user)
        return qs.none()

    EDITABLE_STATUSES = {Contract.Status.DRAFT, Contract.Status.REJECTED}

    def _check_editable(self, contract):
        from rest_framework.exceptions import PermissionDenied

        user = self._current_user()
        if user and user.is_admin:
            return
        if contract.status not in self.EDITABLE_STATUSES:
            raise PermissionDenied(
                'Shartnoma tasdiqqa yuborilgan — qatorlarni faqat admin o\'zgartiradi.',
            )

    def _resync_total(self, contract):
        """Qator o'zgardi — summa qayta yig'iladi (QQS bilan), bron moslashadi."""
        from apps.inventory.services import sync_contract_reservations

        contract.refresh_from_db()
        contract.total_amount = contract.items_total_with_vat
        contract.save(update_fields=['total_amount'])
        sync_contract_reservations(contract)

    def perform_create(self, serializer):
        contract = serializer.validated_data.get('contract')
        if contract is not None:
            self._check_editable(contract)
        super().perform_create(serializer)
        self._resync_total(serializer.instance.contract)

    def perform_update(self, serializer):
        self._check_editable(serializer.instance.contract)
        super().perform_update(serializer)
        self._resync_total(serializer.instance.contract)

    def perform_destroy(self, instance):
        contract = instance.contract
        self._check_editable(contract)
        super().perform_destroy(instance)
        self._resync_total(contract)


class ContractPaymentViewSet(BaseModelViewSet):
    """To'lovlar. POST ham `confirm-payment` bilan bir xil yo'ldan o'tadi.

    Qo'shimcha to'lov shu yerdan yuborilsa ham: kassaga kirim yoziladi,
    birinchi to'lovda muddat sanog'i boshlanib mahsulot ombordan chiqadi,
    balans yopilsa shartnoma `completed` bo'ladi. `paid_at` ixtiyoriy.
    """

    queryset = ContractPayment.objects.select_related('contract', 'created_by').all()
    serializer_class = ContractPaymentSerializer
    permission_classes = [IsAdminOrBugalter]
    filterset_fields = ['contract', 'method', 'is_prepayment']

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_admin or user.is_bugalter:
            return qs
        if user.is_sales:
            return qs.filter(contract__created_by=user)
        return qs.none()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Yuborilmagan bo'lsa None — servis o'zi aniqlaydi (birinchi to'lov = oldindan)
        is_prepayment = (
            data.get('is_prepayment') if 'is_prepayment' in request.data else None
        )
        payment = confirm_payment(
            data['contract'], request.user,
            amount=data['amount'],
            method=data.get('method', ContractPayment.Method.TRANSFER),
            paid_at=data.get('paid_at'),
            is_prepayment=is_prepayment,
        )
        self.log_action(
            ActivityLog.Action.CREATE, payment,
            f"{payment.contract.number} bo'yicha to'lov: {payment.amount}",
        )
        return Response(self.get_serializer(payment).data, status=201)


class ContractApprovalViewSet(BaseModelViewSet):
    """Tasdiqlash tarixi — faqat o'qish uchun."""

    queryset = ContractApproval.objects.select_related('contract', 'decided_by').all()
    serializer_class = ContractApprovalSerializer
    filterset_fields = ['contract', 'step', 'decision']

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user.is_admin or user.is_bugalter:
            return qs
        if user.is_sales:
            return qs.filter(contract__created_by=user)
        return qs.none()


class LeadViewSet(BaseModelViewSet):
    """Og'zaki kelishuv jarayoni."""

    queryset = Lead.objects.select_related('client', 'contract', 'created_by').all()
    serializer_class = LeadSerializer
    permission_classes = [IsAdminOrSales, IsOwnerOrAdmin]
    search_fields = ['title', 'client__full_name', 'client__company_name']
    filterset_fields = ['stage', 'client', 'created_by']
    ordering_fields = ['created_at', 'next_contact_at']

    def get_queryset(self):
        """EGALIK §3.2: kelishuv — shaxsiy quvur, sales faqat o'zinikini ko'radi."""
        qs = super().get_queryset()
        user = self.request.user
        if user.is_admin:
            return qs
        if user.is_sales:
            return qs.filter(created_by=user)
        return qs.none()
