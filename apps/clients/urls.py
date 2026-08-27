"""clients marshrutlari: mijozlar (jismoniy va yuridik shaxs)."""

from django.urls import path

from apps.clients.views import ClientViewSet

urlpatterns = [
    path('clients/', ClientViewSet.as_view({
        'get': 'list',
        'post': 'create',
    }), name='client-list'),
    path('clients/<int:pk>/', ClientViewSet.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy',
    }), name='client-detail'),
]
