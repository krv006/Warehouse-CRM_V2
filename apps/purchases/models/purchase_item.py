from django.db.models import (
    CASCADE,
    PROTECT,
    CharField,
    DecimalField,
    ForeignKey,
)

from apps.core.models import TimeStampedModel


class PurchaseItem(TimeStampedModel):
    """Kirim hujjatining qatori."""

    purchase = ForeignKey('purchases.Purchase', CASCADE, related_name='items')
    product = ForeignKey('inventory.Product', PROTECT, related_name='purchase_items')
    quantity = DecimalField(max_digits=18, decimal_places=2, default=1)
    unit_price = DecimalField(max_digits=18, decimal_places=2, default=0)
    note = CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.product} x {self.quantity}'

    @property
    def subtotal(self):
        return self.quantity * self.unit_price
