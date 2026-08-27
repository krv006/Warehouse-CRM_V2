from django.db.models import (
    CASCADE,
    SET_NULL,
    CharField,
    DateTimeField,
    ForeignKey,
    TextChoices,
    TextField,
)

from apps.core.models import TimeStampedModel


class ReplenishmentEvent(TimeStampedModel):
    """Yetkazib berish bosqichlari — jarayon shaffof ko'rinishi uchun (TZ 7.3)."""

    class Stage(TextChoices):
        ORDERED = 'ordered', 'Buyurtma berildi'
        SHIPPED = 'shipped', 'Jo\u2019natildi'
        CUSTOMS = 'customs', 'Bojxonada'
        CLEARED = 'cleared', 'Bojxonadan chiqdi'
        ARRIVED = 'arrived', 'Yetib keldi'
        NOTE = 'note', 'Izoh'

    replenishment = ForeignKey('procurement.Replenishment', CASCADE, related_name='events')
    stage = CharField(max_length=20, choices=Stage.choices)
    comment = TextField(blank=True)
    happened_at = DateTimeField()
    created_by = ForeignKey(
        'accounts.User', SET_NULL, related_name='replenishment_events',
        null=True, blank=True,
    )

    class Meta:
        ordering = ['happened_at', 'id']

    def __str__(self):
        return f'{self.replenishment} — {self.get_stage_display()}'
