from django.db.models import (
    CASCADE,
    PROTECT,
    CharField,
    DecimalField,
    ForeignKey,
)

from apps.core.models import TimeStampedModel


class ReplenishmentItem(TimeStampedModel):
    """To'ldirish qatori — Buyurtmachi ta'minotchidan narx shakllantiradi."""

    replenishment = ForeignKey('procurement.Replenishment', CASCADE, related_name='items')
    product = ForeignKey('inventory.Product', PROTECT, related_name='replenishment_items')
    quantity = DecimalField(max_digits=18, decimal_places=2, default=1)
    unit_price = DecimalField(max_digits=18, decimal_places=2, default=0)
    supplier = CharField(max_length=200, blank=True)
    note = CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.product} x {self.quantity}'

    @property
    def subtotal(self):
        return self.quantity * self.unit_price

    @property
    def needs_price(self):
        return not self.unit_price
