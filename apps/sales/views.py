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
    filterset_fields = ['status', 'client', 'currency']
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
    queryset = ContractPayment.objects.select_related('contract', 'created_by').all()
    serializer_class = ContractPaymentSerializer
    permission_classes = [IsAdminOrBugalter]
    filterset_fields = ['contract', 'method', 'is_prepayment']


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
