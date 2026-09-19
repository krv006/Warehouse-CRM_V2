from django.db.models import (
    CASCADE,
    SET_NULL,
    CharField,
    ForeignKey,
    TextChoices,
    TextField,
)

from apps.core.models import TimeStampedModel


class ConfigurationRequestEvent(TimeStampedModel):
    """Zayavka hayotidagi qadam — izohi bilan (YANGI-OQIM B15).

    §2.1 aylanmasi ko'p marta aylanadi: rad etish, qayta yuborish, narx
    so'rovi statusda iz qoldirmaydi — bitta izoh maydoni yetmaydi, oldingi
    izohlar ustiga yozilib yo'qolardi. TLD dagi `ReplenishmentEvent` bilan
    bir xil shakl. Roadmap (B8) aylanma qadamlarni faqat shu yerdan o'qiydi.
    """

    class Stage(TextChoices):
        CREATED = 'created', 'Zayavka yozildi'
        TAKEN = 'taken', 'Engineer ishga oldi'
        RETURNED = 'returned', "Engineer qaytardi (sales'ga)"
        # 9-to'plam §2: muammo zayavkada emas, engineerda (vaqti yo'q) —
        # ish hovuzga qaytadi, boshqa engineer oladi
        RELEASED = 'released', 'Engineer ishni qaytardi (hovuzga)'
        RESENT = 'resent', 'Sales tuzatib qayta yubordi'
        PRICE_ASKED = 'price_asked', "Narx so'raldi (buyurtmachiga)"
        PRICE_GIVEN = 'price_given', 'Narx kiritildi'
        CANCELLED = 'cancelled', 'Zanjir bekor qilindi'
        NOTE = 'note', 'Izoh'

    request = ForeignKey(
        'configurator.ConfigurationRequest', CASCADE, related_name='events',
    )
    stage = CharField(max_length=20, choices=Stage.choices)
    comment = TextField(blank=True)
    created_by = ForeignKey(
        'accounts.User', SET_NULL, related_name='configuration_request_events',
        null=True, blank=True,
    )

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.request} — {self.get_stage_display()}'
