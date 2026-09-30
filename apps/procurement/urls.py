"""procurement marshrutlari: omborni to'ldirish (Buyurtmachi)."""

from django.urls import path

from apps.core.routing import DETAIL, LIST, READ_DETAIL, READ_LIST
from apps.procurement.views import (
    ImportCostSheetViewSet,
    PriceRequestLineViewSet,
    PriceRequestViewSet,
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

    # 24-to'plam: import tannarx varaqasi — generic POST/PATCH yo'q, har
    # bo'lim o'z amali orqali (§6.3). 29-§6: `open` OLIB TASHLANDI —
    # `request_prices` (28-to'plam) bu varaqani endi ochmaydi.
    path('import-cost-sheets/', ImportCostSheetViewSet.as_view(READ_LIST), name='importcostsheet-list'),
    path('import-cost-sheets/<int:pk>/', ImportCostSheetViewSet.as_view(READ_DETAIL), name='importcostsheet-detail'),
    path('import-cost-sheets/<int:pk>/fill-goods/', ImportCostSheetViewSet.as_view({
        'post': 'fill_goods',
    }), name='importcostsheet-fill-goods'),
    path('import-cost-sheets/<int:pk>/fill-logistics/', ImportCostSheetViewSet.as_view({
        'post': 'fill_logistics',
    }), name='importcostsheet-fill-logistics'),
    path('import-cost-sheets/<int:pk>/fill-customs/', ImportCostSheetViewSet.as_view({
        'post': 'fill_customs',
    }), name='importcostsheet-fill-customs'),
    path('import-cost-sheets/<int:pk>/return/', ImportCostSheetViewSet.as_view({
        'post': 'return_sheet',
    }), name='importcostsheet-return'),
    path('import-cost-sheets/<int:pk>/cancel/', ImportCostSheetViewSet.as_view({
        'post': 'cancel',
    }), name='importcostsheet-cancel'),
    path('import-cost-sheets/<int:pk>/change-quantity/', ImportCostSheetViewSet.as_view({
        'post': 'change_quantity',
    }), name='importcostsheet-change-quantity'),

    # 28-to'plam: narx so'rovi — bitta hujjat, uch rol, bir-birini ko'rmaydi
    path('price-requests/', PriceRequestViewSet.as_view(READ_LIST), name='pricerequest-list'),
    path('price-requests/<int:pk>/', PriceRequestViewSet.as_view(READ_DETAIL), name='pricerequest-detail'),
    path('price-requests/<int:pk>/cancel/', PriceRequestViewSet.as_view({
        'post': 'cancel',
    }), name='pricerequest-cancel'),

    path('price-request-lines/<int:pk>/', PriceRequestLineViewSet.as_view(READ_DETAIL), name='pricerequestline-detail'),
    path('price-request-lines/<int:pk>/fill-logistics/', PriceRequestLineViewSet.as_view({
        'post': 'fill_logistics',
    }), name='pricerequestline-fill-logistics'),
    path('price-request-lines/<int:pk>/fill-customs/', PriceRequestLineViewSet.as_view({
        'post': 'fill_customs',
    }), name='pricerequestline-fill-customs'),
    path('price-request-lines/<int:pk>/send-to-customs/', PriceRequestLineViewSet.as_view({
        'post': 'send_to_customs',
    }), name='pricerequestline-send-to-customs'),
    path('price-request-lines/<int:pk>/mark-imported/', PriceRequestLineViewSet.as_view({
        'post': 'mark_imported',
    }), name='pricerequestline-mark-imported'),
    path('price-request-lines/<int:pk>/answer/', PriceRequestLineViewSet.as_view({
        'post': 'answer',
    }), name='pricerequestline-answer'),
    path('price-request-lines/<int:pk>/return/', PriceRequestLineViewSet.as_view({
        'post': 'return_line',
    }), name='pricerequestline-return'),
]
