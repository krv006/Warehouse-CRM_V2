from django.core.exceptions import ValidationError
from django.db.models import BooleanField, CharField, TextField

from apps.core.models import TimeStampedModel


class Warehouse(TimeStampedModel):
    """Jismoniy ombor.

    Biznesda BITTA ombor ishlatiladi — filial degan tushuncha yo'q.
    Ikkinchi ombor yaratishga urinish xato beradi; barcha jarayonlar
    yagona omborni `apps.inventory.services.main_warehouse()` orqali oladi.
    """

    name = CharField(max_length=150)
    address = TextField(blank=True)
    is_active = BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if Warehouse.objects.exclude(pk=self.pk).exists():
            raise ValidationError(
                "Biznesda bitta ombor ishlatiladi — ikkinchi ombor qo'shilmaydi."
            )
        super().save(*args, **kwargs)
