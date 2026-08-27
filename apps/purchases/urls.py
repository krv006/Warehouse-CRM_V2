"""purchases marshrutlari: kirim hujjatlari."""

from django.urls import path

from apps.core.routing import DETAIL, LIST
from apps.purchases.views import (
    PurchaseViewSet,
    PurchaseItemViewSet,
    PurchaseDocumentViewSet,
)

urlpatterns = [
    path('purchases/', PurchaseViewSet.as_view(LIST), name='purchase-list'),
    path('purchases/in-transit/', PurchaseViewSet.as_view({
        'get': 'in_transit',
    }), name='purchase-in-transit'),
    path('purchases/<int:pk>/', PurchaseViewSet.as_view(DETAIL), name='purchase-detail'),
    path('purchases/<int:pk>/receive/', PurchaseViewSet.as_view({
        'post': 'receive',
    }), name='purchase-receive'),
    path('purchases/<int:pk>/timeline/', PurchaseViewSet.as_view({
        'get': 'timeline',
    }), name='purchase-timeline'),

    path('purchase-items/', PurchaseItemViewSet.as_view(LIST), name='purchaseitem-list'),
    path('purchase-items/<int:pk>/', PurchaseItemViewSet.as_view(DETAIL), name='purchaseitem-detail'),

    path('purchase-documents/', PurchaseDocumentViewSet.as_view(LIST), name='purchasedocument-list'),
    path('purchase-documents/<int:pk>/', PurchaseDocumentViewSet.as_view(DETAIL), name='purchasedocument-detail'),
]
