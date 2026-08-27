from django.db.models import (
    PROTECT,
    SET_NULL,
    CharField,
    DateTimeField,
    DecimalField,
    ForeignKey,
    TextField,
)

from apps.core.choices import Currency, Direction
from apps.core.models import TimeStampedModel


class CashTransaction(TimeStampedModel):
    """Kassa harakati — barcha kirim va chiqimlar shu yerda nazorat qilinadi."""

    direction = CharField(max_length=10, choices=Direction.choices, blank=True)
    category = ForeignKey('finance.CashCategory', PROTECT, related_name='transactions')
    amount = DecimalField(max_digits=18, decimal_places=2)
    currency = CharField(max_length=3, choices=Currency.choices, default=Currency.UZS)
    exchange_rate = DecimalField(max_digits=18, decimal_places=4, default=1)
    occurred_at = DateTimeField()
    description = TextField(blank=True)

    contract = ForeignKey(
        'sales.Contract', SET_NULL, related_name='cash_transactions',
        null=True, blank=True,
    )
    purchase = ForeignKey(
        'purchases.Purchase', SET_NULL, related_name='cash_transactions',
        null=True, blank=True,
    )
    loan = ForeignKey(
        'finance.Loan', SET_NULL, related_name='cash_transactions',
        null=True, blank=True,
    )
    expense_request = ForeignKey(
        'finance.ExpenseRequest', SET_NULL, related_name='cash_transactions',
        null=True, blank=True,
    )
    created_by = ForeignKey(
        'accounts.User', SET_NULL, related_name='cash_transactions',
        null=True, blank=True,
    )
    approved_by = ForeignKey(
        'accounts.User', SET_NULL, related_name='approved_cash_transactions',
        null=True, blank=True,
    )

    class Meta:
        ordering = ['-occurred_at']

    def __str__(self):
        return f'{self.get_direction_display()} {self.amount} — {self.category}'

    def save(self, *args, **kwargs):
        if self.category_id:
            self.direction = self.category.direction
        super().save(*args, **kwargs)

    @property
    def amount_uzs(self):
        return self.amount * self.exchange_rate
