from django.db.models import (
    CASCADE,
    PROTECT,
    CharField,
    ForeignKey,
    PositiveIntegerField,
    UniqueConstraint,
)

from apps.core.models import TimeStampedModel


class ProductSpec(TimeStampedModel):
    """Bazaviy modelning zavod tarkibi (HP 880 ichidagi SSD 512 GB kabi)."""

    product = ForeignKey('inventory.Product', CASCADE, related_name='specs')
    component = ForeignKey('inventory.Product', PROTECT, related_name='spec_usages')
    label = CharField(max_length=100, blank=True)
    quantity = PositiveIntegerField(default=1)

    class Meta:
        ordering = ['label', 'id']
        constraints = [
            UniqueConstraint(
                fields=['product', 'component'],
                name='uniq_product_spec_component',
            ),
        ]

    def __str__(self):
        return f'{self.product} — {self.component} x {self.quantity}'
