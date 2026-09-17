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
    def _planned_left(self):
        """Rejadan keyingi XOM qoldiq — manfiy bo'lishi mumkin (ichki hisob)."""
        from apps.inventory.services import plannable_quantity

        return plannable_quantity(
            self.component, self.configuration.warehouse,
            for_configuration=self.configuration,
        )

    @property
    def available(self):
        """Rejadan keyin qolgan qoldiq (§11.4): Jami − Band − boshqalar rejasi.

        Engineer xavfsiz raqamni ko'radi — boshqa shartnoma va konfiguratsiyalarga
        va'da qilingan mol "bor" bo'lib ko'rinmaydi; o'z rejasi hisobga olinmaydi.
        3-to'plam §3: 0 dan past tushmaydi — ekranda "omborda -6" o'rniga
        "omborda 0" + alohida `overbooked` chiqadi.
        """
        return max(self._planned_left, 0)

    @property
    def overbooked(self):
        """Boshqa hujjatlarga zaxiradan ORTIQCHA va'da qilingani (3-to'plam §3).

        Bron turgan mol keyin chiqim bo'lib ketsa reja qoldig'i manfiyga
        tushadi — front "omborda 0, ustiga N dona ortiqcha va'da qilingan"
        deb aniq yozadi. `shortage` bu teshikni ham yopib buyurtma qiladi.
        """
        return max(-self._planned_left, 0)

    @property
    def stock_total(self):
        """Ombordagi jami qoldiq — bronlarni hisobga olmagan xom raqam."""
        from apps.inventory.services import available_quantity

        return available_quantity(self.component, self.configuration.warehouse)

    @property
    def total_needed(self):
        """Butun partiya uchun kerak: qator miqdori × konfiguratsiya miqdori (#3)."""
        return self.quantity * self.configuration.quantity

    @property
    def shortage(self):
        # Xom qoldiqdan: manfiy bo'lsa buyurtma teshikni ham yopadi (§3)
        return max(self.total_needed - self._planned_left, 0)

    @property
    def source(self):
        return 'stock' if self.shortage == 0 else 'purchase'
