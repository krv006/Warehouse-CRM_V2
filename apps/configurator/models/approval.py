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
        # 9-to'plam §1: engineer'ning aniqlashtirish savoli ham shu tarixda —
        # ro'yxat ikki tomonlama suhbatga aylanadi (savol → javob → tasdiq)
        ENGINEER = 'engineer', 'Engineer savoli'

    class Decision(TextChoices):
        APPROVED = 'approved', 'Tasdiqlandi'
        REJECTED = 'rejected', 'Qaytarildi'
        QUESTION = 'question', "So'rov"
        ANSWER = 'answer', 'Javob'

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

    class Meta:
        # 9-to'plam §1: ro'yxat suhbat tartibida o'qiladi (savol → javob → ...)
        ordering = ['created_at']

    def __str__(self):
        return f'{self.configuration} — {self.get_decision_display()}'
