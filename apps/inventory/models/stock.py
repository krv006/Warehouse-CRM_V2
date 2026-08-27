from django.db.models import CASCADE, DecimalField, ForeignKey, UniqueConstraint

from apps.core.models import TimeStampedModel


class Stock(TimeStampedModel):
    """Mahsulotning ombordagi qoldigi."""

    product = ForeignKey('inventory.Product', CASCADE, related_name='stocks')
    warehouse = ForeignKey('inventory.Warehouse', CASCADE, related_name='stocks')
    quantity = DecimalField(max_digits=14, decimal_places=2, default=0)

    class Meta:
        constraints = [
            UniqueConstraint(
                fields=['product', 'warehouse'],
                name='uniq_product_warehouse',
            ),
        ]

    def __str__(self):
        return f'{self.product} @ {self.warehouse}: {self.quantity}'
