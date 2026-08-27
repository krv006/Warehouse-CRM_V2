from django.db.models import (
    PROTECT,
    SET_NULL,
    CharField,
    DecimalField,
    ForeignKey,
    TextChoices,
)

from apps.core.models import TimeStampedModel


class StockMovement(TimeStampedModel):
    """Kirim / chiqim / tuzatish harakati."""

    class Type(TextChoices):
        IN = 'in', 'Kirim'
        OUT = 'out', 'Chiqim'
        ADJUST = 'adjust', 'Tuzatish'

    class Reason(TextChoices):
        PURCHASE = 'purchase', 'Kirim hujjati'
        SALE = 'sale', 'Sotuv'
        CONFIGURATION = 'configuration', 'Configurator'
        MANUAL = 'manual', "Qo'lda"

    product = ForeignKey('inventory.Product', PROTECT, related_name='movements')
    warehouse = ForeignKey('inventory.Warehouse', PROTECT, related_name='movements')
    type = CharField(max_length=10, choices=Type.choices)
    reason = CharField(max_length=20, choices=Reason.choices, default=Reason.MANUAL)
    quantity = DecimalField(max_digits=18, decimal_places=2)
    reference = CharField(max_length=100, blank=True)
    note = CharField(max_length=255, blank=True)
    created_by = ForeignKey(
        'accounts.User', SET_NULL, related_name='movements',
        null=True, blank=True,
    )

    def __str__(self):
        return f'{self.get_type_display()} {self.quantity} — {self.product}'
