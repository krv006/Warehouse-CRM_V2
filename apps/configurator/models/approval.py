from django.db.models import (
    CASCADE,
    SET_NULL,
    CharField,
    ForeignKey,
    TextChoices,
    TextField,
)

from apps.core.models import TimeStampedModel


class ConfigurationApproval(TimeStampedModel):
    """Konfiguratsiya texnik tasdig'ining tarixi (TOPSHIRIQ-2 #4).

    Sales mijozga ko'rsatib "shu tarkib to'g'rimi?" savoliga javob beradi —
    har bir qaror (tasdiq yoki izoh bilan qaytarish) shu yerda qoladi.
    Narx tasdig'i boshqa narsa — u TLD zanjiridagi `pending_sales` bosqichi.
    """

    class Step(TextChoices):
        SALES = 'sales', 'Sales — texnik yechim'

    class Decision(TextChoices):
        APPROVED = 'approved', 'Tasdiqlandi'
        REJECTED = 'rejected', 'Qaytarildi'

    configuration = ForeignKey(
        'configurator.Configuration', CASCADE, related_name='approvals',
    )
    step = CharField(max_length=20, choices=Step.choices, default=Step.SALES)
    decision = CharField(max_length=20, choices=Decision.choices)
    comment = TextField(blank=True)
    decided_by = ForeignKey(
        'accounts.User', SET_NULL, related_name='configuration_approvals',
        null=True, blank=True,
    )

    def __str__(self):
        return f'{self.configuration} — {self.get_decision_display()}'
