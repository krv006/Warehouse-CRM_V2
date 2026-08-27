from django.db.models import (
    PROTECT,
    SET_NULL,
    CharField,
    DateTimeField,
    DecimalField,
    ForeignKey,
    TextChoices,
    TextField,
)

from apps.core.choices import Currency
from apps.core.models import TimeStampedModel


class ExpenseRequest(TimeStampedModel):
    """Bugalter pul chiqarish uchun admindan so'raydigan ruxsat (TZ: bugalter roli)."""

    class Status(TextChoices):
        PENDING = 'pending', 'Kutilmoqda'
        APPROVED = 'approved', 'Ruxsat berildi'
        REJECTED = 'rejected', 'Rad etildi'

    category = ForeignKey('finance.CashCategory', PROTECT, related_name='expense_requests')
    amount = DecimalField(max_digits=18, decimal_places=2)
    currency = CharField(max_length=3, choices=Currency.choices, default=Currency.UZS)
    purpose = TextField()
    status = CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    comment = TextField(blank=True)
    requested_by = ForeignKey(
        'accounts.User', SET_NULL, related_name='expense_requests',
        null=True, blank=True,
    )
    decided_by = ForeignKey(
        'accounts.User', SET_NULL, related_name='decided_expense_requests',
        null=True, blank=True,
    )
    decided_at = DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'{self.amount} — {self.get_status_display()}'
