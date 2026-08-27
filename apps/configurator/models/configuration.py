from django.db.models import (
    PROTECT,
    SET_NULL,
    CharField,
    ForeignKey,
    TextChoices,
    TextField,
)

from apps.core.models import TimeStampedModel
from apps.core.utils import next_number


class Configuration(TimeStampedModel):
    """Bazaviy model ustidan yig'ilgan mijoz konfiguratsiyasi (chernovik)."""

    class Status(TextChoices):
        DRAFT = 'draft', 'Chernovik'
        READY = 'ready', 'Tayyor'
        ATTACHED = 'attached', 'Buyurtmaga biriktirilgan'
        CANCELLED = 'cancelled', 'Bekor qilingan'

    number = CharField(max_length=30, unique=True, blank=True)
    client = ForeignKey(
        'clients.Client', PROTECT, related_name='configurations',
        null=True, blank=True,
    )
    base_product = ForeignKey('inventory.Product', PROTECT, related_name='configurations')
    warehouse = ForeignKey(
        'inventory.Warehouse', PROTECT, related_name='configurations',
        null=True, blank=True,
    )
    act = ForeignKey(
        'configurator.Act', PROTECT, related_name='configurations',
        null=True, blank=True,
    )
    purchase = ForeignKey(
        'purchases.Purchase', SET_NULL, related_name='configurations',
        null=True, blank=True,
    )
    status = CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    note = TextField(blank=True)
    created_by = ForeignKey(
        'accounts.User', SET_NULL, related_name='configurations',
        null=True, blank=True,
    )

    def __str__(self):
        return f'{self.number} — {self.base_product}'

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = next_number(Configuration, 'CFG')
        super().save(*args, **kwargs)

    @property
    def total_price(self):
        return sum((item.subtotal for item in self.items.all()), 0)

    @property
    def missing_items(self):
        """Omborda yetishmayotgan, ya'ni kirim qilinishi kerak bo'lgan qatorlar."""
        return [item for item in self.items.all() if item.shortage > 0]
