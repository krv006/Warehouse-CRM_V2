from django.core.exceptions import ValidationError
from django.db.models import CharField, EmailField, TextField

from apps.core.models.base import TimeStampedModel


class CompanyProfile(TimeStampedModel):
    """Bajaruvchi (o'z firmamiz) rekvizitlari — shartnoma chop etishda ishlatiladi.

    Tizimda bitta yozuv bo'ladi (singleton): admin to'ldiradi, qolganlar o'qiydi.
    """

    name = CharField(max_length=200, blank=True)
    inn = CharField('STIR / INN', max_length=20, blank=True)
    phone = CharField(max_length=20, blank=True)
    email = EmailField(blank=True)
    address = CharField(max_length=300, blank=True)
    bank_name = CharField(max_length=200, blank=True)
    mfo = CharField(max_length=10, blank=True)
    account_number = CharField(max_length=30, blank=True)
    director_name = CharField(max_length=200, blank=True)
    contract_terms = TextField(
        blank=True,
        help_text="Shartnoma chop etilganda chiqadigan standart shartlar matni",
    )

    def __str__(self):
        return self.name or 'Bajaruvchi rekvizitlari'

    def save(self, *args, **kwargs):
        if CompanyProfile.objects.exclude(pk=self.pk).exists():
            raise ValidationError(
                "Bajaruvchi rekvizitlari bitta bo'ladi — mavjudini tahrirlang.",
            )
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """Yagona yozuvni qaytaradi, bo'lmasa bo'sh holda ochadi."""
        profile = cls.objects.first()
        if profile is None:
            profile = cls.objects.create()
        return profile
