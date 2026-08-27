from django.db.models import (
    CASCADE,
    PROTECT,
    CharField,
    DecimalField,
    ForeignKey,
    PositiveIntegerField,
)

from apps.core.models import TimeStampedModel


class ConfigurationItem(TimeStampedModel):
    """Konfiguratsiya qatori — mijoz tanlagan butlovchi."""

    configuration = ForeignKey('configurator.Configuration', CASCADE, related_name='items')
    component = ForeignKey('inventory.Product', PROTECT, related_name='configuration_items')
    label = CharField(max_length=100, blank=True)
    quantity = PositiveIntegerField(default=1)
    unit_price = DecimalField(max_digits=18, decimal_places=2, default=0)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.component} x {self.quantity}'

    def save(self, *args, **kwargs):
        # TZ 6.2: narx kiritilmagan bo'lsa, ombordagi narx avtomatik olinadi
        if not self.unit_price and self.component_id:
            self.unit_price = self.component.stock_price
        super().save(*args, **kwargs)

    @property
    def stock_price(self):
        return self.component.stock_price

    @property
    def needs_price(self):
        """Omborda ham, qatorda ham narx yo'q — foydalanuvchi kiritishi kerak."""
        return not self.unit_price

    @property
    def subtotal(self):
        return self.quantity * self.unit_price

    @property
    def available(self):
        from apps.inventory.services import available_quantity

        return available_quantity(self.component, self.configuration.warehouse)

    @property
    def shortage(self):
        return max(self.quantity - self.available, 0)

    @property
    def source(self):
        return 'stock' if self.shortage == 0 else 'purchase'
