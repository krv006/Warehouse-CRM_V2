from django.db.models import (
    SET_NULL,
    BooleanField,
    CharField,
    DateField,
    ForeignKey,
    TextChoices,
    TextField,
)

from apps.core.models.base import TimeStampedModel


class Notification(TimeStampedModel):
    """Muddat eslatmalari (shartnoma, qarz, import)."""

    class Level(TextChoices):
        INFO = 'info', "Ma'lumot"
        WARNING = 'warning', 'Ogohlantirish'
        DANGER = 'danger', 'Shoshilinch'

    user = ForeignKey(
        'accounts.User', SET_NULL, related_name='notifications',
        null=True, blank=True,
    )
    title = CharField(max_length=200)
    message = TextField(blank=True)
    level = CharField(max_length=20, choices=Level.choices, default=Level.INFO)
    entity = CharField(max_length=100, blank=True)
    object_id = CharField(max_length=50, blank=True)
    due_date = DateField(null=True, blank=True)
    is_read = BooleanField(default=False)

    def __str__(self):
        return self.title
