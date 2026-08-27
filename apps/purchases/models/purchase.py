from datetime import timedelta

from django.db.models import (
    PROTECT,
    SET_NULL,
    CharField,
    DateField,
    DecimalField,
    ForeignKey,
    PositiveIntegerField,
    TextChoices,
    TextField,
)

from apps.core.choices import Currency
from apps.core.models import TimeStampedModel
from apps.core.utils import deadline_progress, next_number


class Purchase(TimeStampedModel):
    """Kirim hujjati: O'zbekiston ichidan, import yoki ustav orqali."""

    class Type(TextChoices):
        LOCAL = 'local', "O'zbekiston ichidan"
        IMPORT = 'import', 'Import'
        USTAV = 'ustav', 'Ustav (USTAF)'

    class Status(TextChoices):
        DRAFT = 'draft', 'Qoralama'
        ORDERED = 'ordered', 'Zakaz qilingan'
        IN_TRANSIT = 'in_transit', "Yo'lda"
        RECEIVED = 'received', 'Qabul qilindi'
        CANCELLED = 'cancelled', 'Bekor qilingan'

    number = CharField(max_length=30, unique=True, blank=True)
    type = CharField(max_length=20, choices=Type.choices, default=Type.LOCAL)
    status = CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    supplier = CharField(max_length=200)
    warehouse = ForeignKey('inventory.Warehouse', PROTECT, related_name='purchases')
    contract = ForeignKey(
        'sales.Contract', SET_NULL, related_name='purchases',
        null=True, blank=True,
    )
    currency = CharField(max_length=3, choices=Currency.choices, default=Currency.UZS)
    exchange_rate = DecimalField(max_digits=18, decimal_places=4, default=1)

    # Import muddati — line chart uchun kunlar sanog'i
    lead_days = PositiveIntegerField(default=0)
    ordered_at = DateField(null=True, blank=True)
    expected_at = DateField(null=True, blank=True)
    received_at = DateField(null=True, blank=True)

    # USTAF: bojxona boji va soliq
    customs_duty = DecimalField(max_digits=18, decimal_places=2, default=0)
    tax_amount = DecimalField(max_digits=18, decimal_places=2, default=0)

    invoice_number = CharField(max_length=50, blank=True)
    note = TextField(blank=True)
    created_by = ForeignKey(
        'accounts.User', SET_NULL, related_name='purchases',
        null=True, blank=True,
    )

    def __str__(self):
        return f'{self.number} — {self.get_type_display()}'

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = next_number(Purchase, 'KIR')
        if self.ordered_at and self.lead_days and not self.expected_at:
            self.expected_at = self.ordered_at + timedelta(days=self.lead_days)
        super().save(*args, **kwargs)

    @property
    def items_total(self):
        return sum((item.subtotal for item in self.items.all()), 0)

    @property
    def total_amount(self):
        return self.items_total + self.customs_duty + self.tax_amount

    @property
    def progress(self):
        """Import kunlarining line chart ma'lumoti."""
        return deadline_progress(self.ordered_at, self.lead_days)

    @property
    def days_left(self):
        return self.progress['days_left']

    @property
    def color(self):
        return self.progress['color']
