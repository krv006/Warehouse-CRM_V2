from decimal import Decimal

from django.db.models import (
    PROTECT,
    SET_NULL,
    CharField,
    DateField,
    DecimalField,
    ForeignKey,
    PositiveIntegerField,
    Sum,
    TextChoices,
    TextField,
)

from apps.core.choices import Currency
from apps.core.models import TimeStampedModel
from apps.core.utils import deadline_progress, next_number

# TZ: 1 mlrd dan kam bo'lsa 30%, ko'p bo'lsa 15% oldindan to'lov
PREPAYMENT_THRESHOLD = Decimal('1000000000')
PREPAYMENT_PERCENT_SMALL = Decimal('30')
PREPAYMENT_PERCENT_LARGE = Decimal('15')


def default_prepayment_percent(total_amount):
    """Shartnoma summasiga qarab oldindan to'lov foizi."""
    total = Decimal(total_amount or 0)
    if total < PREPAYMENT_THRESHOLD:
        return PREPAYMENT_PERCENT_SMALL
    return PREPAYMENT_PERCENT_LARGE


class Contract(TimeStampedModel):
    """Sales tomonidan tuziladigan shartnoma va uning tasdiqlash zanjiri."""

    class Status(TextChoices):
        DRAFT = 'draft', 'Qoralama'
        PENDING_BUGALTER = 'pending_bugalter', 'Bugalter tasdig\'i kutilmoqda'
        PENDING_ADMIN = 'pending_admin', 'Admin tasdig\'i kutilmoqda'
        APPROVED = 'approved', 'Tasdiqlandi, pul kutilmoqda'
        ACTIVE = 'active', 'Pul keldi, muddat ketmoqda'
        COMPLETED = 'completed', 'Yakunlandi'
        REJECTED = 'rejected', 'Rad etildi'
        CANCELLED = 'cancelled', 'Bekor qilingan'

    number = CharField(max_length=30, unique=True, blank=True)
    client = ForeignKey('clients.Client', PROTECT, related_name='contracts')
    configuration = ForeignKey(
        'configurator.Configuration', SET_NULL, related_name='contracts',
        null=True, blank=True,
    )
    status = CharField(max_length=30, choices=Status.choices, default=Status.DRAFT)
    currency = CharField(max_length=3, choices=Currency.choices, default=Currency.UZS)
    total_amount = DecimalField(max_digits=18, decimal_places=2, default=0)
    prepayment_percent = DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
    )
    term_days = PositiveIntegerField(default=90)
    signed_at = DateField(null=True, blank=True)
    start_date = DateField(null=True, blank=True)
    note = TextField(blank=True)
    created_by = ForeignKey(
        'accounts.User', SET_NULL, related_name='contracts',
        null=True, blank=True,
    )

    def __str__(self):
        return self.number

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = next_number(Contract, 'SHT')
        if self.prepayment_percent is None:
            self.prepayment_percent = default_prepayment_percent(self.total_amount)
        super().save(*args, **kwargs)

    @property
    def items_total(self):
        return sum((item.subtotal for item in self.items.all()), Decimal('0'))

    @property
    def prepayment_amount(self):
        percent = self.prepayment_percent or default_prepayment_percent(self.total_amount)
        return (Decimal(self.total_amount or 0) * percent / Decimal('100')).quantize(Decimal('0.01'))

    @property
    def paid(self):
        return self.payments.aggregate(t=Sum('amount'))['t'] or Decimal('0')

    @property
    def balance(self):
        return Decimal(self.total_amount or 0) - self.paid

    @property
    def progress(self):
        """Line chart: pul kelgan kundan boshlab muddat sanog'i."""
        return deadline_progress(self.start_date, self.term_days)

    @property
    def days_left(self):
        return self.progress['days_left']

    @property
    def color(self):
        return self.progress['color']
