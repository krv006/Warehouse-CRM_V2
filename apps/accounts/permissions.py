from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.accounts.models import User


def _authenticated(user):
    return bool(user and user.is_authenticated)


def _has_role(user, *roles):
    return _authenticated(user) and (user.is_admin or user.role in roles)


class IsAdmin(BasePermission):
    """Faqat admin."""

    message = 'Bu amal faqat admin uchun.'

    def has_permission(self, request, view):
        return _authenticated(request.user) and request.user.is_admin


class IsAdminOrReadOnly(BasePermission):
    """O'qish — hammaga, yozish — adminga."""

    message = "O'zgartirish faqat admin uchun."

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return _authenticated(request.user)
        return _authenticated(request.user) and request.user.is_admin


class IsAdminOrBugalter(BasePermission):
    """Pul va hujjat qismlari: yozish admin yoki bugalterga."""

    message = 'Bu amal admin yoki bugalter uchun.'

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return _authenticated(request.user)
        return _has_role(request.user, User.Role.BUGALTER)


class IsAdminOrSales(BasePermission):
    """Sotuv qismlari: yozish admin yoki salesga."""

    message = 'Bu amal admin yoki sales uchun.'

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return _authenticated(request.user)
        return _has_role(request.user, User.Role.SALES)


class IsAdminOrSupplier(BasePermission):
    """Omborni to'ldirish qismi: yozish admin yoki buyurtmachiga."""

    message = 'Bu amal admin yoki buyurtmachi uchun.'

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return _authenticated(request.user)
        return _has_role(request.user, User.Role.SUPPLIER)


class CanManageClients(BasePermission):
    """Client qo'shish Sales va Buyurtmachida bor, Bugalterda yo'q (TZ 11)."""

    message = "Client qo'shish bugalter uchun mavjud emas."

    def has_permission(self, request, view):
        if not _authenticated(request.user):
            return False
        if request.method in SAFE_METHODS:
            return True
        return not request.user.is_bugalter
