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

from apps.core.models import TimeStampedModel


class Lead(TimeStampedModel):
    """Og'zaki kelishuv jarayoni — shartnomagacha bo'lgan bosqichlar."""

    class Stage(TextChoices):
        NEW = 'new', 'Yangi'
        NEGOTIATION = 'negotiation', 'Muzokara'
        VERBAL = 'verbal', "Og'zaki kelishuv"
        CONTRACT = 'contract', 'Shartnomaga o\'tdi'
        LOST = 'lost', "Yo'qotildi"

    client = ForeignKey('clients.Client', PROTECT, related_name='leads')
    title = CharField(max_length=200)
    stage = CharField(max_length=20, choices=Stage.choices, default=Stage.NEW)
    expected_amount = DecimalField(max_digits=18, decimal_places=2, default=0)
    next_contact_at = DateTimeField(null=True, blank=True)
    note = TextField(blank=True)
    contract = ForeignKey(
        'sales.Contract', SET_NULL, related_name='leads',
        null=True, blank=True,
    )
    created_by = ForeignKey(
        'accounts.User', SET_NULL, related_name='leads',
        null=True, blank=True,
    )

    def __str__(self):
        return f'{self.title} — {self.get_stage_display()}'
