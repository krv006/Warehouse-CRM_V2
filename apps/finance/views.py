from django.db.models import Sum
from django.utils.timezone import now
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST

from apps.accounts.permissions import FinanceAccess, IsAdmin
from apps.core.choices import Direction
from apps.core.mixins import BaseModelViewSet
from apps.core.models import ActivityLog, Notification
from apps.finance.models import CashCategory, CashTransaction, ExpenseRequest, Loan
from apps.finance.serializers import (
    CashCategorySerializer,
    CashTransactionSerializer,
    ExpenseRequestSerializer,
    LoanSerializer,
)
from apps.finance.services import record_transaction

# Xarajatga ruxsatni faqat admin beradi (TZ: bugalter roli)
ADMIN_ACTIONS = {'approve', 'reject'}


class CashCategoryViewSet(BaseModelViewSet):
    """Kassa yacheykalari — yangi xarajat turini qo'shish mumkin."""

    queryset = CashCategory.objects.all()
    serializer_class = CashCategorySerializer
    permission_classes = [FinanceAccess]
    search_fields = ['name', 'code']
    filterset_fields = ['direction', 'is_active', 'is_system']


class CashTransactionViewSet(BaseModelViewSet):
    """Kassa: barcha kirim va chiqimlar nazorati."""

    queryset = (
        CashTransaction.objects
        .select_related('category', 'contract', 'purchase', 'loan', 'created_by')
        .all()
    )
    serializer_class = CashTransactionSerializer
    permission_classes = [FinanceAccess]
    search_fields = ['description']
    filterset_fields = ['direction', 'category', 'currency', 'contract', 'purchase', 'loan']
    ordering_fields = ['occurred_at', 'amount']

    def summary(self, request):
        """GET /cash-transactions/summary/ — kirim va chiqim hisoboti."""
        queryset = self.filter_queryset(self.get_queryset())
        by_category = list(
            queryset
            .values('direction', 'category__code', 'category__name')
            .annotate(total=Sum('amount'))
            .order_by('direction', '-total')
        )
        income = queryset.filter(direction=Direction.IN).aggregate(t=Sum('amount'))['t'] or 0
        expense = queryset.filter(direction=Direction.OUT).aggregate(t=Sum('amount'))['t'] or 0
        return Response({
            'income_total': income,
            'expense_total': expense,
            'balance': income - expense,
            'by_category': by_category,
        })


class LoanViewSet(BaseModelViewSet):
    """Qarzlar — muddat va summa nazorati, eslatma bilan."""

    queryset = Loan.objects.select_related('created_by').prefetch_related('cash_transactions').all()
    serializer_class = LoanSerializer
    permission_classes = [FinanceAccess]
    search_fields = ['lender_name']
    filterset_fields = ['status', 'currency', 'source']
    ordering_fields = ['deadline', 'amount']

    def perform_create(self, serializer):
        loan = serializer.save(created_by=self._current_user())
        record_transaction(
            code='loan',
            amount=loan.amount,
            occurred_at=now(),
            description=f'{loan.lender_name} dan qarz',
            currency=loan.currency,
            loan=loan,
            user=self._current_user(),
        )
        self.log_action(ActivityLog.Action.CREATE, loan)

    def repay(self, request, pk=None):
        """POST /loans/{id}/repay/ — qarzni qisman yoki to'liq qaytarish."""
        loan = self.get_object()
        amount = request.data.get('amount') or loan.balance
        record_transaction(
            code='loan_repay',
            amount=amount,
            occurred_at=now(),
            description=f'{loan.lender_name} ga qarz qaytarildi',
            currency=loan.currency,
            loan=loan,
            user=self._current_user(),
        )
        if loan.balance <= 0:
            loan.status = Loan.Status.CLOSED
            loan.save()
        self.log_action(ActivityLog.Action.UPDATE, loan, f'Qarz qaytarildi: {amount}')
        return Response(self.get_serializer(loan).data)


class ExpenseRequestViewSet(BaseModelViewSet):
    """Bugalterning pul chiqarish so'rovi — adminning ruxsati bilan."""

    queryset = (
        ExpenseRequest.objects
        .select_related('category', 'requested_by', 'decided_by')
        .all()
    )
    serializer_class = ExpenseRequestSerializer
    permission_classes = [FinanceAccess]
    filterset_fields = ['status', 'category', 'requested_by']
    ordering_fields = ['created_at', 'amount']

    def get_permissions(self):
        if self.action in ADMIN_ACTIONS:
            return [IsAdmin()]
        return super().get_permissions()

    def perform_create(self, serializer):
        expense_request = serializer.save(requested_by=self._current_user())
        self.log_action(ActivityLog.Action.CREATE, expense_request)

    def _decide(self, request, status):
        expense_request = self.get_object()
        if expense_request.status != ExpenseRequest.Status.PENDING:
            return None, Response(
                {'detail': "So'rov allaqachon ko'rib chiqilgan."},
                status=HTTP_400_BAD_REQUEST,
            )
        expense_request.status = status
        expense_request.decided_by = self._current_user()
        expense_request.decided_at = now()
        expense_request.comment = request.data.get('comment', '')
        expense_request.save()
        return expense_request, None

    def approve(self, request, pk=None):
        """POST /expense-requests/{id}/approve/ — admin ruxsati, kassaga chiqim."""
        expense_request, error = self._decide(request, ExpenseRequest.Status.APPROVED)
        if error:
            return error

        record_transaction(
            code=expense_request.category.code,
            amount=expense_request.amount,
            occurred_at=now(),
            description=expense_request.purpose,
            currency=expense_request.currency,
            expense_request=expense_request,
            user=expense_request.requested_by,
            approved_by=self._current_user(),
        )
        self.log_action(ActivityLog.Action.APPROVE, expense_request, 'Xarajatga ruxsat berildi')
        return Response(self.get_serializer(expense_request).data)

    def reject(self, request, pk=None):
        """POST /expense-requests/{id}/reject/ — rad etish va bugalterga eslatma."""
        expense_request, error = self._decide(request, ExpenseRequest.Status.REJECTED)
        if error:
            return error

        Notification.objects.create(
            user=expense_request.requested_by,
            title="Xarajat so'rovi rad etildi",
            message=expense_request.comment,
            level=Notification.Level.WARNING,
            entity='ExpenseRequest',
            object_id=str(expense_request.pk),
        )
        self.log_action(ActivityLog.Action.REJECT, expense_request, expense_request.comment)
        return Response(self.get_serializer(expense_request).data)
