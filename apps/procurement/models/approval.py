from django.db.models import (
    CASCADE,
    SET_NULL,
    CharField,
    ForeignKey,
    TextChoices,
    TextField,
)

from apps.core.models import TimeStampedModel


class ReplenishmentApproval(TimeStampedModel):
    """Tasdiqlash zanjiri: buyurtmachi -> bugalter -> admin (TZ 9)."""

    class Step(TextChoices):
        BUGALTER = 'bugalter', 'Bugalter tekshiruvi'
        ADMIN = 'admin', 'Admin tasdig\u2019i'

    class Decision(TextChoices):
        APPROVED = 'approved', 'Tasdiqlandi'
        REJECTED = 'rejected', 'Rad etildi'

    replenishment = ForeignKey('procurement.Replenishment', CASCADE, related_name='approvals')
    step = CharField(max_length=20, choices=Step.choices)
    decision = CharField(max_length=20, choices=Decision.choices)
    comment = TextField(blank=True)
    decided_by = ForeignKey(
        'accounts.User', SET_NULL, related_name='replenishment_approvals',
        null=True, blank=True,
    )

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.replenishment} — {self.get_step_display()}'
