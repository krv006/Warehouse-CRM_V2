from django.contrib.admin import ModelAdmin, register

from apps.finance.models import CashCategory, CashTransaction, ExpenseRequest, Loan


@register(CashCategory)
class CashCategoryAdmin(ModelAdmin):
    list_display = ['name', 'code', 'direction', 'is_system', 'is_active']
    list_filter = ['direction', 'is_system', 'is_active']


@register(CashTransaction)
class CashTransactionAdmin(ModelAdmin):
    list_display = ['occurred_at', 'direction', 'category', 'amount', 'currency']
    list_filter = ['direction', 'category', 'currency']


@register(Loan)
class LoanAdmin(ModelAdmin):
    list_display = ['lender_name', 'amount', 'taken_at', 'deadline', 'status']
    list_filter = ['status', 'currency']


@register(ExpenseRequest)
class ExpenseRequestAdmin(ModelAdmin):
    list_display = ['amount', 'category', 'status', 'requested_by', 'decided_by', 'decided_at']
    list_filter = ['status', 'category']
