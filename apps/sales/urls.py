"""sales marshrutlari: og'zaki kelishuv va shartnomalar."""

from django.urls import path

from apps.core.routing import DETAIL, LIST, READ_DETAIL, READ_LIST
from apps.sales.views import (
    ContractViewSet,
    ContractItemViewSet,
    ContractApprovalViewSet,
    ContractPaymentViewSet,
    LeadViewSet,
)

urlpatterns = [
    path('leads/', LeadViewSet.as_view(LIST), name='lead-list'),
    path('leads/<int:pk>/', LeadViewSet.as_view(DETAIL), name='lead-detail'),

    path('contracts/', ContractViewSet.as_view(LIST), name='contract-list'),
    path('contracts/deadlines/', ContractViewSet.as_view({
        'get': 'deadlines',
    }), name='contract-deadlines'),
    path('contracts/<int:pk>/', ContractViewSet.as_view(DETAIL), name='contract-detail'),
    path('contracts/<int:pk>/submit/', ContractViewSet.as_view({
        'post': 'submit',
    }), name='contract-submit'),
    path('contracts/<int:pk>/approve/', ContractViewSet.as_view({
        'post': 'approve',
    }), name='contract-approve'),
    path('contracts/<int:pk>/reject/', ContractViewSet.as_view({
        'post': 'reject',
    }), name='contract-reject'),
    path('contracts/<int:pk>/confirm-payment/', ContractViewSet.as_view({
        'post': 'confirm_payment',
    }), name='contract-confirm-payment'),
    path('contracts/<int:pk>/timeline/', ContractViewSet.as_view({
        'get': 'timeline',
    }), name='contract-timeline'),

    path('contract-items/', ContractItemViewSet.as_view(LIST), name='contractitem-list'),
    path('contract-items/<int:pk>/', ContractItemViewSet.as_view(DETAIL), name='contractitem-detail'),

    path('contract-payments/', ContractPaymentViewSet.as_view(LIST), name='contractpayment-list'),
    path('contract-payments/<int:pk>/', ContractPaymentViewSet.as_view(DETAIL), name='contractpayment-detail'),

    path('contract-approvals/', ContractApprovalViewSet.as_view(READ_LIST), name='contractapproval-list'),
    path('contract-approvals/<int:pk>/', ContractApprovalViewSet.as_view(READ_DETAIL), name='contractapproval-detail'),
]
