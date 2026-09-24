from django.db.models import (
    CASCADE,
    SET_NULL,
    CharField,
    ForeignKey,
    TextChoices,
    TextField,
)

from apps.core.models import TimeStampedModel


class ActApproval(TimeStampedModel):
    """ACT tasdig'i tarixi (20-§3) — `ContractApproval`/`ConfigurationApproval`/
    `ReplenishmentApproval` bilan bir xil naqsh: qaytarish izohi engineer
    uchun, tasdiq esa huquqiy hujjat uchun kerak.
    """

    class Decision(TextChoices):
        APPROVED = 'approved', 'Tasdiqlandi'
        REJECTED = 'rejected', 'Qaytarildi'

    act = ForeignKey('configurator.Act', CASCADE, related_name='approvals')
    decision = CharField(max_length=20, choices=Decision.choices)
    comment = TextField(blank=True)
    decided_by = ForeignKey(
        'accounts.User', SET_NULL, related_name='act_approvals',
        null=True, blank=True,
    )

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.act} — {self.get_decision_display()}'
