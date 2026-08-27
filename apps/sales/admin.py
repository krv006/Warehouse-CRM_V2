from django.contrib.admin import ModelAdmin, TabularInline, register

from apps.sales.models import (
    Contract,
    ContractItem,
    ContractApproval,
    ContractPayment,
    Lead,
)


class ContractItemInline(TabularInline):
    model = ContractItem
    extra = 1


class ContractPaymentInline(TabularInline):
    model = ContractPayment
    extra = 0


class ContractApprovalInline(TabularInline):
    model = ContractApproval
    extra = 0


@register(Contract)
class ContractAdmin(ModelAdmin):
    list_display = ['number', 'client', 'status', 'total_amount', 'prepayment_percent', 'start_date']
    list_filter = ['status', 'currency']
    search_fields = ['number']
    inlines = [ContractItemInline, ContractPaymentInline, ContractApprovalInline]


@register(Lead)
class LeadAdmin(ModelAdmin):
    list_display = ['title', 'client', 'stage', 'expected_amount', 'next_contact_at']
    list_filter = ['stage']
