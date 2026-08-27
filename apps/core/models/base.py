from django.db.models import Model, DateTimeField


class TimeStampedModel(Model):
    """Barcha modellar uchun umumiy vaqt maydonlari."""

    created_at = DateTimeField(auto_now_add=True)
    updated_at = DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ['-created_at']
