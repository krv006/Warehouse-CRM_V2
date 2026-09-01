"""accounts marshrutlari: foydalanuvchilar va JWT."""

from django.urls import path

from apps.accounts.views import LoginView, RefreshView, UserViewSet

urlpatterns = [
    path('auth/login/', LoginView.as_view(), name='token_obtain_pair'),
    path('auth/refresh/', RefreshView.as_view(), name='token_refresh'),

    path('users/', UserViewSet.as_view({
        'get': 'list',
        'post': 'create',
    }), name='user-list'),
    path('users/me/', UserViewSet.as_view({
        'get': 'me',
    }), name='user-me'),
    path('users/<int:pk>/', UserViewSet.as_view({
        'get': 'retrieve',
        'put': 'update',
        'patch': 'partial_update',
        'delete': 'destroy',
    }), name='user-detail'),
]
