from django.db.models import (
    CASCADE,
    SET_NULL,
    CharField,
    ForeignKey,
    TextChoices,
    TextField,
)

from apps.core.models import TimeStampedModel


class ContractApproval(TimeStampedModel):
    """Shartnoma tasdiqlash zanjiri: sales -> bugalter -> admin -> bugalter."""

    class Step(TextChoices):
        BUGALTER = 'bugalter', 'Bugalter'
        ADMIN = 'admin', 'Admin'
        PAYMENT = 'payment', "To'lov tasdig'i"

    class Decision(TextChoices):
        APPROVED = 'approved', 'Tasdiqlandi'
        REJECTED = 'rejected', 'Rad etildi'

    contract = ForeignKey('sales.Contract', CASCADE, related_name='approvals')
    step = CharField(max_length=20, choices=Step.choices)
    decision = CharField(max_length=20, choices=Decision.choices)
    comment = TextField(blank=True)
    decided_by = ForeignKey(
        'accounts.User', SET_NULL, related_name='contract_approvals',
        null=True, blank=True,
    )

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.contract} — {self.get_step_display()}: {self.get_decision_display()}'
