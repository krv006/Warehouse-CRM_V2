from django.contrib.admin import ModelAdmin, TabularInline, register

from apps.sales.models import (
    Contract,
    ContractItem,
    ContractApproval,
    ContractPayment,
    ContractDocument,
    ContractDocumentVersion,
    ContractTemplate,
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


class ContractDocumentVersionInline(TabularInline):
    model = ContractDocumentVersion
    extra = 0


@register(ContractDocument)
class ContractDocumentAdmin(ModelAdmin):
    list_display = ['contract', 'template', 'updated_by', 'updated_at']
    inlines = [ContractDocumentVersionInline]


@register(ContractTemplate)
class ContractTemplateAdmin(ModelAdmin):
    list_display = ['name', 'language', 'is_active', 'is_default', 'created_by']
    list_filter = ['language', 'is_active', 'is_default']
