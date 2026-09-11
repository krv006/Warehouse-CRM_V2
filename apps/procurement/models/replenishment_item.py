from django.db.models import (
    CASCADE,
    PROTECT,
    CharField,
    DecimalField,
    ForeignKey,
)

from apps.core.models import TimeStampedModel
from apps.core.utils import vat_amount_of


class ReplenishmentItem(TimeStampedModel):
    """To'ldirish qatori — Buyurtmachi ta'minotchidan narx shakllantiradi.

    `unit_price` — QQS'siz narx. QQS default 0: ta'minotchi hisobida QQS
    bo'lsa buyurtmachi foizini o'zi kiritadi (masalan 12).
    """

    replenishment = ForeignKey('procurement.Replenishment', CASCADE, related_name='items')
    product = ForeignKey('inventory.Product', PROTECT, related_name='replenishment_items')
    quantity = DecimalField(max_digits=18, decimal_places=2, default=1)
    unit_price = DecimalField(max_digits=18, decimal_places=2, default=0)
    vat_percent = DecimalField('QQS %', max_digits=5, decimal_places=2, default=0)
    supplier = CharField(max_length=200, blank=True)
    note = CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.product} x {self.quantity}'

    @property
    def subtotal(self):
        """QQS'siz qator summasi."""
        return self.quantity * self.unit_price

    @property
    def vat_amount(self):
        return vat_amount_of(self.subtotal, self.vat_percent)

    @property
    def total_with_vat(self):
        """Qator jami — QQS bilan."""
        return self.subtotal + self.vat_amount

    @property
    def needs_price(self):
        return not self.unit_price
