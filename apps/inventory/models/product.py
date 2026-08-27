from django.db.models import (
    SET_NULL,
    BooleanField,
    CharField,
    DecimalField,
    ForeignKey,
    PositiveIntegerField,
    Sum,
    TextChoices,
    TextField,
)

from apps.core.models import TimeStampedModel


class Product(TimeStampedModel):
    """Ombordagi mahsulot: bazaviy model yoki uning butlovchisi (TZ 6.1).

    Katalog ma'lumotnoma hisoblanadi — TZ mahsulot omborda mavjud deb qaraydi.
    Qoldiq esa faqat Kirim va Chiqim jarayonlari orqali o'zgaradi (TZ 1-bo'lim).
    """

    class Kind(TextChoices):
        MACHINE = 'machine', 'Tayyor model'
        COMPONENT = 'component', 'Butlovchi'
        OTHER = 'other', 'Boshqa'

    sku = CharField(max_length=50, unique=True)
    name = CharField(max_length=200)
    kind = CharField(max_length=20, choices=Kind.choices, default=Kind.MACHINE)
    description = TextField(blank=True)
    cost_price = DecimalField(max_digits=18, decimal_places=2, default=0)
    sale_price = DecimalField(max_digits=18, decimal_places=2, default=0)

    # TZ 7.1: qoldiq shu darajadan pastga tushsa, to'ldirish ro'yxatiga tushadi
    reorder_level = PositiveIntegerField(default=0)
    is_active = BooleanField(default=True)

    # Configurator yaratgan variant uchun: bazaviy model va tarkib imzosi (TZ 6.2)
    base_model = ForeignKey(
        'inventory.Product', SET_NULL, related_name='variants',
        null=True, blank=True,
    )
    signature = CharField(max_length=64, unique=True, null=True, blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.sku})'

    @property
    def is_variant(self):
        return self.base_model_id is not None

    @property
    def stock_price(self):
        """Ombordagi narx: sotuv narxi, bo'lmasa tannarx (TZ 6.2)."""
        return self.sale_price or self.cost_price

    @property
    def total_stock(self):
        return self.stocks.aggregate(t=Sum('quantity'))['t'] or 0

    @property
    def is_low_stock(self):
        return self.total_stock <= self.reorder_level
