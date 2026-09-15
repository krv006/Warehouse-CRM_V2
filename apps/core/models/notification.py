from django.db.models import (
    CASCADE,
    BooleanField,
    CharField,
    DateField,
    ForeignKey,
    TextChoices,
    TextField,
)

from apps.core.models.base import TimeStampedModel


class Notification(TimeStampedModel):
    """Muddat eslatmalari (shartnoma, qarz, import).

    §4.4 (SIDEBAR-VA-EGALIK): `user` MAJBURIY — "e'lon taxtasi" (user=None,
    hammaga ko'rinadigan) xabar taqiqlangan: har bir xabarning aniq egasi
    yoki hovuzi bor, hovuz roldagi har bir odamga alohida yozuv bo'lib tushadi.
    """

    class Level(TextChoices):
        INFO = 'info', "Ma'lumot"
        WARNING = 'warning', 'Ogohlantirish'
        DANGER = 'danger', 'Shoshilinch'

    user = ForeignKey('accounts.User', CASCADE, related_name='notifications')
    title = CharField(max_length=200)
    message = TextField(blank=True)
    level = CharField(max_length=20, choices=Level.choices, default=Level.INFO)
    entity = CharField(max_length=100, blank=True)
    object_id = CharField(max_length=50, blank=True)
    due_date = DateField(null=True, blank=True)
    is_read = BooleanField(default=False)

    def __str__(self):
        return self.title
