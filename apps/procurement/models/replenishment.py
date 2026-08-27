from datetime import timedelta

from django.db.models import (
    PROTECT,
    SET_NULL,
    CharField,
    DateField,
    DecimalField,
    ForeignKey,
    TextChoices,
    TextField,
)

from apps.core.choices import Currency
from apps.core.models import TimeStampedModel
from apps.core.utils import deadline_progress, next_number

# TZ 7.2: qarz mahsulot kelgandan keyin 2 oy ichida qaytariladi
DEBT_TERM_DAYS = 60


class Replenishment(TimeStampedModel):
    """Omborni to'ldirish buyurtmasi — Buyurtmachi rolining asosiy hujjati (TZ 7)."""

    class Status(TextChoices):
        DRAFT = 'draft', 'Qoralama'
        PENDING_BUGALTER = 'pending_bugalter', 'Bugalter tekshiruvida'
        PENDING_ADMIN = 'pending_admin', 'Admin tasdiqlashida'
        APPROVED = 'approved', 'Tasdiqlandi, buyurtma berish mumkin'
        ORDERED = 'ordered', 'Buyurtma berildi'
        IN_TRANSIT = 'in_transit', "Yo'lda"
        CUSTOMS = 'customs', 'Bojxonada'
        DELIVERED = 'delivered', 'Omborga kirim qilindi'
        REJECTED = 'rejected', 'Rad etildi'
        CANCELLED = 'cancelled', 'Bekor qilingan'

    number = CharField(max_length=30, unique=True, blank=True)
    warehouse = ForeignKey('inventory.Warehouse', PROTECT, related_name='replenishments')
    supplier = CharField(max_length=200, blank=True)
    status = CharField(max_length=30, choices=Status.choices, default=Status.DRAFT)
    currency = CharField(max_length=3, choices=Currency.choices, default=Currency.UZS)

    # Buyurtmachi kiritadigan qo'shimcha xarajatlar (TZ 7.1)
    logistics_cost = DecimalField(max_digits=18, decimal_places=2, default=0)
    other_cost = DecimalField(max_digits=18, decimal_places=2, default=0)

    paid_amount = DecimalField(max_digits=18, decimal_places=2, default=0)
    debt = ForeignKey(
        'finance.Loan', SET_NULL, related_name='replenishments',
        null=True, blank=True,
    )

    expected_at = DateField(null=True, blank=True)
    delivered_at = DateField(null=True, blank=True)
    note = TextField(blank=True)
    created_by = ForeignKey(
        'accounts.User', SET_NULL, related_name='replenishments',
        null=True, blank=True,
    )

    def __str__(self):
        return f'{self.number} — {self.get_status_display()}'

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = next_number(Replenishment, 'TLD')
        super().save(*args, **kwargs)

    @property
    def items_total(self):
        return sum((item.subtotal for item in self.items.all()), 0)

    @property
    def total_amount(self):
        """Mahsulotlar + logistika + boshqa xarajatlar."""
        return self.items_total + self.logistics_cost + self.other_cost

    @property
    def cash_available(self):
        """Kassadagi mavjud pul — admin oynasida ko'rinadi (TZ 7.1)."""
        from apps.finance.services import cash_balance

        return cash_balance()

    @property
    def shortfall(self):
        """Yetmayotgan summa — shu qism qarzga o'tqaziladi."""
        return max(self.total_amount - self.cash_available, 0)

    @property
    def debt_progress(self):
        """Qarz muddati: mahsulot kelgan kundan 2 oy (TZ 7.2)."""
        if not self.debt:
            return deadline_progress(None, 0)
        return deadline_progress(self.debt.taken_at, DEBT_TERM_DAYS)

    @property
    def debt_days_left(self):
        return self.debt_progress['days_left']

    @property
    def debt_color(self):
        return self.debt_progress['color']

    @property
    def default_debt_deadline(self):
        from django.utils.timezone import localdate

        return (self.delivered_at or localdate()) + timedelta(days=DEBT_TERM_DAYS)
