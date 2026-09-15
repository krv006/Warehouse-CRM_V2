from rest_framework.serializers import ModelSerializer, ReadOnlyField, ValidationError

from apps.finance.models import CashCategory, CashTransaction, ExpenseRequest, Loan


class CashCategorySerializer(ModelSerializer):
    direction_display = ReadOnlyField(source='get_direction_display')

    class Meta:
        model = CashCategory
        fields = [
            'id', 'code', 'name', 'direction', 'direction_display',
            'is_system', 'is_active',
        ]
        read_only_fields = ['is_system']


class CashTransactionSerializer(ModelSerializer):
    category_name = ReadOnlyField(source='category.name')
    direction_display = ReadOnlyField(source='get_direction_display')
    amount_uzs = ReadOnlyField()
    replenishment_number = ReadOnlyField(source='replenishment.number')

    class Meta:
        model = CashTransaction
        fields = [
            'id', 'direction', 'direction_display', 'category', 'category_name',
            'amount', 'currency', 'exchange_rate', 'amount_uzs', 'occurred_at',
            'description', 'contract', 'purchase', 'loan', 'expense_request',
            'replenishment', 'replenishment_number',
            'created_by', 'approved_by', 'created_at',
        ]
        read_only_fields = ['direction', 'created_by', 'approved_by']


class LoanSerializer(ModelSerializer):
    status_display = ReadOnlyField(source='get_status_display')
    source_display = ReadOnlyField(source='get_source_display')
    days_left = ReadOnlyField()
    color = ReadOnlyField()
    repaid = ReadOnlyField()
    balance = ReadOnlyField()

    class Meta:
        model = Loan
        fields = [
            'id', 'lender_name', 'amount', 'currency', 'taken_at', 'deadline',
            'status', 'status_display', 'source', 'source_display',
            'note', 'days_left', 'color',
            'repaid', 'balance', 'created_by', 'created_at',
        ]
        read_only_fields = ['created_by']


class ExpenseRequestSerializer(ModelSerializer):
    category_name = ReadOnlyField(source='category.name')
    status_display = ReadOnlyField(source='get_status_display')
    requested_by_name = ReadOnlyField(source='requested_by.username')

    def validate_category(self, category):
        """Xarajat so'rovi faqat chiqim yacheykasiga yoziladi.

        Kirim yacheykasi tanlansa, tasdiqda kassaga chiqim o'rniga KIRIM
        yozilib kassa buzilardi (§10.12.1).
        """
        from apps.core.choices import Direction

        if category.direction != Direction.OUT:
            raise ValidationError(
                "Xarajat so'rovi uchun chiqim yacheykasi tanlanadi — "
                f"'{category.name}' kirim yacheykasi.",
            )
        return category

    class Meta:
        model = ExpenseRequest
        fields = [
            'id', 'category', 'category_name', 'amount', 'currency', 'purpose',
            'status', 'status_display', 'comment', 'requested_by', 'requested_by_name',
            'decided_by', 'decided_at', 'created_at',
        ]
        read_only_fields = ['status', 'requested_by', 'decided_by', 'decided_at']
