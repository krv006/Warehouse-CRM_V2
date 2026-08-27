"""procurement marshrutlari: omborni to'ldirish (Buyurtmachi)."""

from django.urls import path

from apps.core.routing import DETAIL, LIST, READ_DETAIL, READ_LIST
from apps.procurement.views import (
    ReplenishmentViewSet,
    ReplenishmentItemViewSet,
    ReplenishmentApprovalViewSet,
    ReplenishmentEventViewSet,
)

urlpatterns = [
    path('replenishments/', ReplenishmentViewSet.as_view(LIST), name='replenishment-list'),
    path('replenishments/low-stock/', ReplenishmentViewSet.as_view({
        'get': 'low_stock',
    }), name='replenishment-low-stock'),
    path('replenishments/from-low-stock/', ReplenishmentViewSet.as_view({
        'post': 'from_low_stock',
    }), name='replenishment-from-low-stock'),
    path('replenishments/<int:pk>/', ReplenishmentViewSet.as_view(DETAIL), name='replenishment-detail'),
    path('replenishments/<int:pk>/submit/', ReplenishmentViewSet.as_view({
        'post': 'submit',
    }), name='replenishment-submit'),
    path('replenishments/<int:pk>/approve/', ReplenishmentViewSet.as_view({
        'post': 'approve',
    }), name='replenishment-approve'),
    path('replenishments/<int:pk>/reject/', ReplenishmentViewSet.as_view({
        'post': 'reject',
    }), name='replenishment-reject'),
    path('replenishments/<int:pk>/pay/', ReplenishmentViewSet.as_view({
        'post': 'pay',
    }), name='replenishment-pay'),
    path('replenishments/<int:pk>/events/', ReplenishmentViewSet.as_view({
        'post': 'add_event',
    }), name='replenishment-add-event'),
    path('replenishments/<int:pk>/receive/', ReplenishmentViewSet.as_view({
        'post': 'receive',
    }), name='replenishment-receive'),
    path('replenishments/<int:pk>/timeline/', ReplenishmentViewSet.as_view({
        'get': 'timeline',
    }), name='replenishment-timeline'),

    path('replenishment-items/', ReplenishmentItemViewSet.as_view(LIST), name='replenishmentitem-list'),
    path('replenishment-items/<int:pk>/', ReplenishmentItemViewSet.as_view(DETAIL), name='replenishmentitem-detail'),

    path('replenishment-approvals/', ReplenishmentApprovalViewSet.as_view(READ_LIST), name='replenishmentapproval-list'),
    path('replenishment-approvals/<int:pk>/', ReplenishmentApprovalViewSet.as_view(READ_DETAIL), name='replenishmentapproval-detail'),

    path('replenishment-events/', ReplenishmentEventViewSet.as_view(READ_LIST), name='replenishmentevent-list'),
    path('replenishment-events/<int:pk>/', ReplenishmentEventViewSet.as_view(READ_DETAIL), name='replenishmentevent-detail'),
]
