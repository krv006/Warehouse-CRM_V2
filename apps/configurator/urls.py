"""configurator marshrutlari: ACT va konfiguratsiyalar."""

from django.urls import path

from apps.configurator.views import (
    ActViewSet,
    ConfigurationViewSet,
    ConfigurationItemViewSet,
    ConfigurationRequestViewSet,
)
from apps.core.routing import DETAIL, LIST

urlpatterns = [
    path('acts/', ActViewSet.as_view(LIST), name='act-list'),
    path('acts/<int:pk>/', ActViewSet.as_view(DETAIL), name='act-detail'),

    path('configurations/', ConfigurationViewSet.as_view(LIST), name='configuration-list'),
    path('configurations/<int:pk>/', ConfigurationViewSet.as_view(DETAIL), name='configuration-detail'),
    path('configurations/<int:pk>/changes/', ConfigurationViewSet.as_view({
        'get': 'changes',
    }), name='configuration-changes'),
    path('configurations/<int:pk>/stock-check/', ConfigurationViewSet.as_view({
        'get': 'stock_check',
    }), name='configuration-stock-check'),
    # #4: texnik tasdiq zanjiri — engineer submit -> sales approve/reject
    path('configurations/<int:pk>/submit/', ConfigurationViewSet.as_view({
        'post': 'submit',
    }), name='configuration-submit'),
    path('configurations/<int:pk>/approve/', ConfigurationViewSet.as_view({
        'post': 'approve',
    }), name='configuration-approve'),
    path('configurations/<int:pk>/reject/', ConfigurationViewSet.as_view({
        'post': 'reject',
    }), name='configuration-reject'),
    path('configurations/<int:pk>/finalize/', ConfigurationViewSet.as_view({
        'post': 'finalize',
    }), name='configuration-finalize'),
    path('configurations/<int:pk>/assemble/', ConfigurationViewSet.as_view({
        'post': 'assemble',
    }), name='configuration-assemble'),
    # 4-to'plam §2: partiya sonini o'zgartirish — yon ta'sirlari bilan
    path('configurations/<int:pk>/change-quantity/', ConfigurationViewSet.as_view({
        'post': 'change_quantity',
    }), name='configuration-change-quantity'),
    path('configurations/<int:pk>/request-procurement/', ConfigurationViewSet.as_view({
        'post': 'request_procurement',
    }), name='configuration-request-procurement'),
    # YANGI-OQIM B2: narx so'rovi — buyurtma emas, buyurtmachi narx kiritib beradi
    path('configurations/<int:pk>/request-prices/', ConfigurationViewSet.as_view({
        'post': 'request_prices',
    }), name='configuration-request-prices'),
    path('configurations/<int:pk>/export-excel/', ConfigurationViewSet.as_view({
        'get': 'export_excel',
    }), name='configuration-export-excel'),
    # B12: zanjirni bekor qilish — sales (egasi) yoki admin
    path('configurations/<int:pk>/cancel/', ConfigurationViewSet.as_view({
        'post': 'cancel',
    }), name='configuration-cancel'),

    path('configuration-requests/', ConfigurationRequestViewSet.as_view(LIST), name='configurationrequest-list'),
    path('configuration-requests/<int:pk>/', ConfigurationRequestViewSet.as_view(DETAIL), name='configurationrequest-detail'),
    path('configuration-requests/<int:pk>/take/', ConfigurationRequestViewSet.as_view({
        'post': 'take',
    }), name='configurationrequest-take'),
    # B15: engineer izoh bilan qaytaradi, sales tuzatib qayta yuboradi
    path('configuration-requests/<int:pk>/reject/', ConfigurationRequestViewSet.as_view({
        'post': 'reject',
    }), name='configurationrequest-reject'),
    path('configuration-requests/<int:pk>/resend/', ConfigurationRequestViewSet.as_view({
        'post': 'resend',
    }), name='configurationrequest-resend'),
    # B17: bekor qilish zayavkadan ham — eng ko'p ishlatiladigan kirish nuqtasi
    path('configuration-requests/<int:pk>/cancel/', ConfigurationRequestViewSet.as_view({
        'post': 'cancel',
    }), name='configurationrequest-cancel'),

    path('configuration-items/', ConfigurationItemViewSet.as_view(LIST), name='configurationitem-list'),
    path('configuration-items/<int:pk>/', ConfigurationItemViewSet.as_view(DETAIL), name='configurationitem-detail'),
]
