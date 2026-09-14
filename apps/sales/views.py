from rest_framework.response import Response

from apps.accounts.permissions import IsAdminOrBugalter, IsAdminOrSales
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
    submit_contract,
)

# Bu amallarni bugalter (va admin) bajaradi, sales emas
BUGALTER_ACTIONS = {'approve', 'reject', 'confirm_payment'}


class ContractViewSet(BaseModelViewSet):
    """Shartnoma: sales tuzadi, bugalter va admin tasdiqlaydi, bugalter pulni yopadi."""

    queryset = (
        Contract.objects
        .select_related('client', 'configuration', 'created_by')
        .prefetch_related('items__product', 'payments', 'approvals__decided_by')
        .all()
    )
    serializer_class = ContractSerializer
    permission_classes = [IsAdminOrSales]
    search_fields = ['number', 'client__full_name', 'client__company_name']
    filterset_fields = ['status', 'client', 'currency', 'configuration']
    ordering_fields = ['created_at', 'number', 'total_amount']

    def get_permissions(self):
        if self.action in BUGALTER_ACTIONS:
            return [IsAdminOrBugalter()]
        return super().get_permissions()

    def submit(self, request, pk=None):
        """POST /contracts/{id}/submit/ — sales bugalterga yuboradi."""
        contract = submit_contract(self.get_object(), request.user)
        self.log_action(ActivityLog.Action.UPDATE, contract, 'Shartnoma bugalterga yuborildi')
        return Response(self.get_serializer(contract).data)

    def approve(self, request, pk=None):
        """POST /contracts/{id}/approve/ — avval bugalter, keyin admin."""
        contract = approve_contract(
            self.get_object(), request.user, request.data.get('comment', ''),
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
        contract = self.get_object()
        payment = confirm_payment(
            contract,
            request.user,
            amount=request.data.get('amount') or contract.prepayment_amount,
            method=request.data.get('method', ContractPayment.Method.TRANSFER),
        )
        contract.refresh_from_db()
        self.log_action(
            ActivityLog.Action.APPROVE, contract, f"To'lov tasdiqlandi: {payment.amount}",
        )
        return Response(self.get_serializer(contract).data)

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
    queryset = ContractItem.objects.select_related('contract', 'product').all()
    serializer_class = ContractItemSerializer
    permission_classes = [IsAdminOrSales]
    filterset_fields = ['contract', 'product']


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


class LeadViewSet(BaseModelViewSet):
    """Og'zaki kelishuv jarayoni."""

    queryset = Lead.objects.select_related('client', 'contract', 'created_by').all()
    serializer_class = LeadSerializer
    permission_classes = [IsAdminOrSales]
    search_fields = ['title', 'client__full_name', 'client__company_name']
    filterset_fields = ['stage', 'client']
    ordering_fields = ['created_at', 'next_contact_at']
