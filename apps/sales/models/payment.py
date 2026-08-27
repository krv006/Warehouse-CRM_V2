from django.db.models import (
    CASCADE,
    SET_NULL,
    BooleanField,
    CharField,
    DateTimeField,
    DecimalField,
    ForeignKey,
    TextChoices,
)

from apps.core.models import TimeStampedModel


class ContractPayment(TimeStampedModel):
    """Shartnoma bo'yicha tushgan pul. Bugalter tasdiqlaydi."""

    class Method(TextChoices):
        CASH = 'cash', 'Naqd'
        CARD = 'card', 'Karta'
        TRANSFER = 'transfer', "O'tkazma"

    contract = ForeignKey('sales.Contract', CASCADE, related_name='payments')
    amount = DecimalField(max_digits=18, decimal_places=2)
    method = CharField(max_length=20, choices=Method.choices, default=Method.TRANSFER)
    paid_at = DateTimeField()
    is_prepayment = BooleanField(default=False)
    created_by = ForeignKey(
        'accounts.User', SET_NULL, related_name='contract_payments',
        null=True, blank=True,
    )
    approved_by = ForeignKey(
        'accounts.User', SET_NULL, related_name='approved_contract_payments',
        null=True, blank=True,
    )

    class Meta:
        ordering = ['-paid_at']

    def __str__(self):
        return f'{self.amount} — {self.contract}'
