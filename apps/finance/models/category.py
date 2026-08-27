from django.db.models import BooleanField, CharField

from apps.core.choices import Direction
from apps.core.models import TimeStampedModel


class CashCategory(TimeStampedModel):
    """Kassa kategoriyasi — har bir kirim va chiqim shu yacheykalar bo'yicha nazorat qilinadi."""

    code = CharField(max_length=50, unique=True)
    name = CharField(max_length=150)
    direction = CharField(max_length=10, choices=Direction.choices)
    is_system = BooleanField(default=False)
    is_active = BooleanField(default=True)

    class Meta:
        ordering = ['direction', 'name']
        verbose_name_plural = 'Cash categories'

    def __str__(self):
        return f'{self.name} ({self.get_direction_display()})'
