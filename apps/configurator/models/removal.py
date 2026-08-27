from django.db.models import (
    CASCADE,
    PROTECT,
    CharField,
    DecimalField,
    ForeignKey,
    PositiveIntegerField,
)

from apps.core.models import TimeStampedModel


class ConfigurationRemoval(TimeStampedModel):
    """Tayyor mahsulotdan yechib olingan butlovchi (TZ 6.2, modify rejimi).

    Yechib olingan qism omborga qaytadi; narxi shu yerda saqlanadi va
    yakunlashda o'zgartirilishi mumkin. ACT bilan birga bugalterga
    "yechib oldik" xabari boradi.
    """

    configuration = ForeignKey('configurator.Configuration', CASCADE, related_name='removals')
    component = ForeignKey('inventory.Product', PROTECT, related_name='configuration_removals')
    quantity = PositiveIntegerField(default=1)
    unit_price = DecimalField(max_digits=18, decimal_places=2, default=0)
    note = CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.component} x {self.quantity} (yechib olindi)'

    @property
    def subtotal(self):
        return self.quantity * self.unit_price
