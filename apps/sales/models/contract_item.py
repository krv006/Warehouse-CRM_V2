from django.db.models import (
    CASCADE,
    PROTECT,
    DecimalField,
    ForeignKey,
    PositiveIntegerField,
)

from apps.core.models import TimeStampedModel


class ContractItem(TimeStampedModel):
    """Shartnoma qatori — sotuv narxi faqat sales va adminga ko'rinadi."""

    contract = ForeignKey('sales.Contract', CASCADE, related_name='items')
    product = ForeignKey('inventory.Product', PROTECT, related_name='contract_items')
    quantity = PositiveIntegerField(default=1)
    unit_price = DecimalField(max_digits=18, decimal_places=2)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.product} x {self.quantity}'

    @property
    def subtotal(self):
        return self.quantity * self.unit_price
