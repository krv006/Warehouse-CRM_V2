from django.db.models import (
    SET_NULL,
    CharField,
    DateField,
    DecimalField,
    ForeignKey,
    Sum,
    TextChoices,
    TextField,
)

from apps.core.choices import Currency
from apps.core.models import TimeStampedModel
from apps.core.utils import deadline_color


class Loan(TimeStampedModel):
    """Qarz — kimdan olindi, qancha va qaysi sanagacha qaytariladi."""

    class Status(TextChoices):
        ACTIVE = 'active', 'Faol'
        CLOSED = 'closed', 'Yopilgan'

    lender_name = CharField(max_length=200)
    amount = DecimalField(max_digits=18, decimal_places=2)
    currency = CharField(max_length=3, choices=Currency.choices, default=Currency.UZS)
    taken_at = DateField()
    deadline = DateField()
    status = CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    note = TextField(blank=True)
    created_by = ForeignKey(
        'accounts.User', SET_NULL, related_name='loans',
        null=True, blank=True,
    )

    class Meta:
        ordering = ['deadline']

    def __str__(self):
        return f'{self.lender_name} — {self.amount}'

    @property
    def term_days(self):
        return (self.deadline - self.taken_at).days

    @property
    def days_left(self):
        from django.utils.timezone import localdate

        return (self.deadline - localdate()).days

    @property
    def color(self):
        if self.status == self.Status.CLOSED:
            return 'green'
        return deadline_color(self.days_left, self.term_days)

    @property
    def repaid(self):
        return self.cash_transactions.aggregate(t=Sum('amount'))['t'] or 0

    @property
    def balance(self):
        return self.amount - self.repaid
