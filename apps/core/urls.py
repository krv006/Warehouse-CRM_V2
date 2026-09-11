"""core marshrutlari: dashboard, audit va eslatmalar."""

from django.urls import path

from apps.core.routing import READ_DETAIL, READ_LIST
from apps.core.views import (
    ActivityLogViewSet,
    CompanyProfileViewSet,
    DashboardView,
    NotificationViewSet,
)

urlpatterns = [
    path('dashboard/', DashboardView.as_view(), name='dashboard'),

    path('company/', CompanyProfileViewSet.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
    }), name='companyprofile-detail'),

    path('activity-logs/', ActivityLogViewSet.as_view(READ_LIST), name='activitylog-list'),
    path('activity-logs/<int:pk>/', ActivityLogViewSet.as_view(READ_DETAIL), name='activitylog-detail'),

    path('notifications/', NotificationViewSet.as_view(READ_LIST), name='notification-list'),
    path('notifications/<int:pk>/', NotificationViewSet.as_view(READ_DETAIL), name='notification-detail'),
    path('notifications/<int:pk>/mark-read/', NotificationViewSet.as_view({
        'post': 'mark_read',
    }), name='notification-mark-read'),
]
