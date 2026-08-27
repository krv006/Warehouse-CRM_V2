from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import User
from apps.accounts.permissions import IsAdmin
from apps.accounts.serializers import UserSerializer, UserCreateSerializer
from apps.core.mixins import BaseModelViewSet


class UserViewSet(BaseModelViewSet):
    queryset = User.objects.all().order_by('username')
    serializer_class = UserSerializer
    permission_classes = [IsAdmin]
    search_fields = ['username', 'first_name', 'last_name', 'email']
    filterset_fields = ['role', 'is_active']

    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        return UserSerializer

    def get_permissions(self):
        if self.action == 'me':
            return [IsAuthenticated()]
        return super().get_permissions()

    def me(self, request):
        """GET /api/users/me/ — kirgan foydalanuvchi."""
        return Response(UserSerializer(request.user).data)
