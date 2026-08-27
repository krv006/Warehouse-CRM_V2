from django.db.models import (
    PROTECT,
    SET_NULL,
    BooleanField,
    CharField,
    DecimalField,
    ForeignKey,
    ImageField,
    PositiveIntegerField,
    Sum,
    TextChoices,
    TextField,
)

from apps.core.models import TimeStampedModel


class Product(TimeStampedModel):
    """Ombordagi mahsulot: tayyor model yoki uning butlovchisi."""

    class Kind(TextChoices):
        MACHINE = 'machine', 'Tayyor model'
        COMPONENT = 'component', 'Butlovchi'
        OTHER = 'other', 'Boshqa'

    class Unit(TextChoices):
        PIECE = 'pcs', 'Dona'
        KG = 'kg', 'Kilogramm'
        LITER = 'l', 'Litr'
        METER = 'm', 'Metr'
        BOX = 'box', 'Quti'

    sku = CharField(max_length=50, unique=True)
    barcode = CharField(max_length=50, blank=True)
    name = CharField(max_length=200)
    kind = CharField(max_length=20, choices=Kind.choices, default=Kind.MACHINE)
    description = TextField(blank=True)
    category = ForeignKey('inventory.Category', PROTECT, related_name='products')
    unit = CharField(max_length=10, choices=Unit.choices, default=Unit.PIECE)
    cost_price = DecimalField(max_digits=18, decimal_places=2, default=0)
    sale_price = DecimalField(max_digits=18, decimal_places=2, default=0)
    reorder_level = PositiveIntegerField(default=0)
    image = ImageField(upload_to='products/', null=True, blank=True)
    is_active = BooleanField(default=True)

    # Configurator yaratgan variant uchun: bazaviy model va tarkib imzosi
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
        """Ombordagi narx: sotuv narxi, bo'lmasa tannarx."""
        return self.sale_price or self.cost_price

    @property
    def total_stock(self):
        return self.stocks.aggregate(t=Sum('quantity'))['t'] or 0

    @property
    def is_low_stock(self):
        return self.total_stock <= self.reorder_level
