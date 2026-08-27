from django.core.exceptions import ValidationError
from django.db.models import (
    SET_NULL,
    CharField,
    EmailField,
    ForeignKey,
    TextChoices,
    TextField,
)

from apps.core.models import TimeStampedModel


class Client(TimeStampedModel):
    """Mijoz — jismoniy yoki yuridik shaxs."""

    class Type(TextChoices):
        INDIVIDUAL = 'individual', 'Jismoniy shaxs'
        LEGAL = 'legal', 'Yuridik shaxs'

    type = CharField(max_length=20, choices=Type.choices, default=Type.INDIVIDUAL)

    # Jismoniy shaxs
    full_name = CharField(max_length=200, blank=True)
    passport = CharField(max_length=20, unique=True, null=True, blank=True)

    # Yuridik shaxs
    company_name = CharField(max_length=200, unique=True, null=True, blank=True)
    inn = CharField(max_length=20, unique=True, null=True, blank=True)
    mfo = CharField(max_length=20, blank=True)
    bank_name = CharField(max_length=200, blank=True)
    account_number = CharField(max_length=30, unique=True, null=True, blank=True)
    director_name = CharField(max_length=200, blank=True)

    # Umumiy
    jshshir = CharField(max_length=20, unique=True, null=True, blank=True)
    phone = CharField(max_length=20, unique=True)
    email = EmailField(blank=True)
    address = TextField(blank=True)
    note = TextField(blank=True)
    created_by = ForeignKey(
        'accounts.User', SET_NULL, related_name='clients',
        null=True, blank=True,
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        if self.type == self.Type.LEGAL:
            return self.company_name or ''
        return self.full_name or ''

    def clean(self):
        errors = {}
        if self.type == self.Type.INDIVIDUAL:
            if not self.full_name:
                errors['full_name'] = 'Jismoniy shaxs uchun F.I.SH majburiy.'
            if not self.passport:
                errors['passport'] = 'Jismoniy shaxs uchun passport majburiy.'
            if not self.jshshir:
                errors['jshshir'] = 'Jismoniy shaxs uchun JSHSHIR majburiy.'
        else:
            if not self.company_name:
                errors['company_name'] = 'Yuridik shaxs uchun kompaniya nomi majburiy.'
            if not self.inn:
                errors['inn'] = 'Yuridik shaxs uchun INN majburiy.'
            if not self.jshshir:
                errors['jshshir'] = 'Yuridik shaxs uchun JSHSHIR majburiy.'
            if not self.mfo:
                errors['mfo'] = 'Yuridik shaxs uchun MFO majburiy.'
            if not self.bank_name:
                errors['bank_name'] = 'Yuridik shaxs uchun bank nomi majburiy.'
            if not self.account_number:
                errors['account_number'] = 'Yuridik shaxs uchun hisob raqam majburiy.'
            if not self.director_name:
                errors['director_name'] = 'Yuridik shaxs uchun rahbar F.I.SH majburiy.'
        if errors:
            raise ValidationError(errors)
