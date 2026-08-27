from django.db.models import BooleanField, CharField, TextField

from apps.core.models import TimeStampedModel


class Warehouse(TimeStampedModel):
    """Jismoniy ombor."""

    name = CharField(max_length=150)
    address = TextField(blank=True)
    is_active = BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name
