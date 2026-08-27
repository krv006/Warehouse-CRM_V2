"""configurator marshrutlari: ACT va konfiguratsiyalar."""

from django.urls import path

from apps.configurator.views import (
    ActViewSet,
    ConfigurationViewSet,
    ConfigurationItemViewSet,
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
    path('configurations/<int:pk>/finalize/', ConfigurationViewSet.as_view({
        'post': 'finalize',
    }), name='configuration-finalize'),
    path('configurations/<int:pk>/attach/', ConfigurationViewSet.as_view({
        'post': 'attach',
    }), name='configuration-attach'),
    path('configurations/<int:pk>/export-excel/', ConfigurationViewSet.as_view({
        'get': 'export_excel',
    }), name='configuration-export-excel'),

    path('configuration-items/', ConfigurationItemViewSet.as_view(LIST), name='configurationitem-list'),
    path('configuration-items/<int:pk>/', ConfigurationItemViewSet.as_view(DETAIL), name='configurationitem-detail'),
]
