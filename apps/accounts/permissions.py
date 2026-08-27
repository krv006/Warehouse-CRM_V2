"""Rol asosidagi ruxsatlar (TZ 8-bo'lim).

Admin har doim hamma narsaga ega. Qolgan rollar uchun har bir sinf
o'qish va yozish ruxsatini alohida belgilaydi:

    read_roles = None  -> barcha login qilganlar o'qiy oladi
    read_roles = (...)  -> faqat shu rollar o'qiy oladi
    write_roles = (...) -> shu rollar yoza oladi
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.accounts.models import User

ADMIN = User.Role.ADMIN
BUGALTER = User.Role.BUGALTER
SALES = User.Role.SALES
SUPPLIER = User.Role.SUPPLIER
ENGINEER = User.Role.ENGINEER


def _authenticated(user):
    return bool(user and user.is_authenticated)


class RoleAccess(BasePermission):
    """Rollar ro'yxati asosidagi asosiy ruxsat sinfi."""

    read_roles = None
    write_roles = ()
    message = 'Bu bo\'lim sizning rolingiz uchun ochiq emas.'

    def has_permission(self, request, view):
        user = request.user
        if not _authenticated(user):
            return False
        if user.is_admin:
            return True
        roles = self.read_roles if request.method in SAFE_METHODS else self.write_roles
        if roles is None:
            return True
        return user.role in roles


class IsAdmin(RoleAccess):
    """Faqat admin."""

    read_roles = ()
    write_roles = ()
    message = 'Bu amal faqat admin uchun.'


class IsAdminOrReadOnly(RoleAccess):
    """O'qish — hammaga, yozish — adminga (ACT)."""

    read_roles = None
    write_roles = ()
    message = "O'zgartirish faqat admin uchun."


class IsAdminOrBugalter(RoleAccess):
    """O'qish hammaga, yozish bugalterga — shartnoma tasdig'i kabi amallar uchun."""

    read_roles = None
    write_roles = (BUGALTER,)
    message = 'Bu amal admin yoki bugalter uchun.'


class IsAdminOrSales(RoleAccess):
    """Sotuv bo'limi: o'qish hammaga, yozish salesga."""

    read_roles = None
    write_roles = (SALES,)
    message = 'Bu amal admin yoki sales uchun.'


class CanManageClients(RoleAccess):
    """Client qo'shish Sales va Buyurtmachida bor, Bugalterda yo'q (TZ 11)."""

    read_roles = None
    write_roles = (SALES, SUPPLIER)
    message = "Client qo'shish bugalter uchun mavjud emas."


class ConfiguratorAccess(RoleAccess):
    """Configurator: hamma ko'radi, yozish — faqat Engineer.

    Sales configurator ishini qilmaydi — u matnli zayavka yuboradi,
    Engineer esa konfiguratsiyani tayyorlab qaytaradi.
    """

    read_roles = None
    write_roles = (ENGINEER,)
    message = 'Konfiguratsiya bilan Engineer ishlaydi.'


class ConfigurationRequestAccess(RoleAccess):
    """Zayavka: sales yozadi, engineer bajaradi, hamma ko'radi."""

    read_roles = None
    write_roles = (SALES, ENGINEER)
    message = 'Zayavka sales va engineer uchun.'


class FinanceAccess(RoleAccess):
    """Kassa, qarz va xarajatlar — faqat admin va bugalter (TZ 8.2)."""

    read_roles = (BUGALTER,)
    write_roles = (BUGALTER,)
    message = 'Kassa bo\'limi admin va bugalter uchun.'


class PurchaseAccess(RoleAccess):
    """Kirim hujjatlari: bugalter yuritadi, buyurtmachi kuzatadi."""

    read_roles = (BUGALTER, SUPPLIER)
    write_roles = (BUGALTER,)
    message = 'Kirim bo\'limi admin, bugalter va buyurtmachi uchun.'


class ProcurementAccess(RoleAccess):
    """Omborni to'ldirish: buyurtmachi yuritadi, bugalter tekshiradi (TZ 7, 9)."""

    read_roles = (BUGALTER, SUPPLIER)
    write_roles = (SUPPLIER,)
    message = "To'ldirish bo'limi admin, bugalter va buyurtmachi uchun."


class ProcurementSharedAccess(ProcurementAccess):
    """Qabul qilish va bosqich qo'shish — buyurtmachi ham, bugalter ham."""

    write_roles = (SUPPLIER, BUGALTER)
