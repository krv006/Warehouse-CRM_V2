from django.db.models import (
    SET_NULL,
    BooleanField,
    CharField,
    DateField,
    FileField,
    ForeignKey,
    TextField,
)

from apps.core.models import TimeStampedModel
from apps.core.validators import document_extension_validator, validate_upload_size


class Act(TimeStampedModel):
    """ACT — model tarkibini o'zgartirishga asos bo'ladigan hujjat. Sales bosqichida kiritiladi."""

    number = CharField(max_length=50, unique=True)
    title = CharField(max_length=200)
    description = TextField(blank=True)
    issued_at = DateField()
    file = FileField(
        upload_to='acts/', null=True, blank=True,
        validators=[document_extension_validator, validate_upload_size],
    )
    is_active = BooleanField(default=True)
    created_by = ForeignKey(
        'accounts.User', SET_NULL, related_name='acts',
        null=True, blank=True,
    )

    def __str__(self):
        return f'{self.number} — {self.title}'
