from rest_framework.permissions import SAFE_METHODS, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.accounts.models import User
from apps.accounts.permissions import IsAdmin, UserDirectoryAccess
from apps.accounts.serializers import UserSerializer, UserCreateSerializer
from apps.core.mixins import BaseModelViewSet


class LoginView(TokenObtainPairView):
    """JWT login. Brute-force himoyasi: IP bo'yicha daqiqasiga 30 urinish."""

    throttle_scope = 'login'


class RefreshView(TokenRefreshView):
    """JWT yangilash — login bilan bir xil chegarada."""

    throttle_scope = 'login'


class UserViewSet(BaseModelViewSet):
    """Foydalanuvchilar.

    O'qish — admin va bugalter (EGALIK §5.3: bugalter "Xodim" filtrini
    to'ldirishi va oylik yozishi uchun xodimlarni to'liq ko'radi); yozish
    (yaratish, rol berish) — **faqat admin**: aks holda bugalter o'ziga
    admin roli berib qo'ya olardi.
    """

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
        if self.request.method in SAFE_METHODS:
            return [UserDirectoryAccess()]
        return super().get_permissions()

    def me(self, request):
        """GET /api/users/me/ — kirgan foydalanuvchi."""
        return Response(UserSerializer(request.user).data)
