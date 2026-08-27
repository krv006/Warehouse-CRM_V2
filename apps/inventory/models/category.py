from django.db.models import SET_NULL, CharField, ForeignKey

from apps.core.models import TimeStampedModel


class Category(TimeStampedModel):
    """Mahsulot kategoriyasi (ierarxik)."""

    name = CharField(max_length=150)
    parent = ForeignKey(
        'inventory.Category', SET_NULL, related_name='children',
        null=True, blank=True,
    )

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Categories'

    def __str__(self):
        return self.name
