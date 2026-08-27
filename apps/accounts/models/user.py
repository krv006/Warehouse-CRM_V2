from django.contrib.auth.models import AbstractUser
from django.db.models import CharField, TextChoices


class User(AbstractUser):
    """Rol va til bilan kengaytirilgan foydalanuvchi."""

    class Role(TextChoices):
        ADMIN = 'admin', 'Administrator'
        BUGALTER = 'bugalter', 'Bugalter'
        SALES = 'sales', 'Sales'
        SUPPLIER = 'buyurtmachi', 'Buyurtmachi'
        ENGINEER = 'engineer', 'Engineer'

    class Language(TextChoices):
        UZ = 'uz', "O'zbekcha"
        RU = 'ru', 'Русский'
        EN = 'en', 'English'

    role = CharField(max_length=20, choices=Role.choices, default=Role.SALES)
    phone = CharField(max_length=20, blank=True)
    language = CharField(max_length=5, choices=Language.choices, default=Language.UZ)

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    @property
    def is_bugalter(self):
        return self.role == self.Role.BUGALTER

    @property
    def is_sales(self):
        return self.role == self.Role.SALES

    @property
    def is_supplier(self):
        """Buyurtmachi — omborni to'ldirish jarayoniga mas'ul."""
        return self.role == self.Role.SUPPLIER

    @property
    def is_engineer(self):
        """Engineer — configurator ishlari to'liq unga tegishli."""
        return self.role == self.Role.ENGINEER
