from django.db.models import (
    PROTECT,
    SET_NULL,
    CharField,
    ForeignKey,
    PositiveIntegerField,
    TextChoices,
    TextField,
)

from apps.core.models import StatusTrackedModel
from apps.core.utils import next_number


class ConfigurationRequest(StatusTrackedModel):
    """Sales'dan Engineerga boradigan matnli zayavka.

    Sales client bilan gaplashib zakazni matn ko'rinishida yozadi va yuboradi.
    Engineer uni oladi, configuratorda tayyorlaydi va konfiguratsiyani
    biriktirib qaytaradi — sales shundan keyin shartnoma jarayonini boshlaydi.
    """

    class Status(TextChoices):
        NEW = 'new', 'Yangi'
        IN_PROGRESS = 'in_progress', 'Engineer ishlamoqda'
        DONE = 'done', 'Konfiguratsiya tayyor'
        # Shartnoma ochilgach zayavka arxivga o'tadi — navbatlarda ko'rinmaydi
        ARCHIVED = 'archived', 'Arxivlangan'
        CANCELLED = 'cancelled', 'Bekor qilingan'

    number = CharField(max_length=30, unique=True, blank=True)
    client = ForeignKey(
        'clients.Client', PROTECT, related_name='configuration_requests',
        null=True, blank=True,
    )
    text = TextField(help_text='Client xohishi — sales yozgan matn')
    # #3: mijoz nechta so'ragani — sales yozadi, take'da konfiguratsiyaga ko'chadi
    quantity = PositiveIntegerField(default=1)
    base_product = ForeignKey(
        'inventory.Product', PROTECT, related_name='configuration_requests',
        null=True, blank=True,
        help_text="Sales taxmin qilgan bazaviy model — take'da shu bo'yicha konfiguratsiya ochiladi",
    )
    warehouse = ForeignKey(
        'inventory.Warehouse', PROTECT, related_name='configuration_requests',
        null=True, blank=True,
    )
    status = CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    configuration = ForeignKey(
        'configurator.Configuration', SET_NULL, related_name='requests',
        null=True, blank=True,
    )
    taken_by = ForeignKey(
        'accounts.User', SET_NULL, related_name='taken_configuration_requests',
        null=True, blank=True,
    )
    created_by = ForeignKey(
        'accounts.User', SET_NULL, related_name='configuration_requests',
        null=True, blank=True,
    )

    def __str__(self):
        return f'{self.number} — {self.get_status_display()}'

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = next_number(ConfigurationRequest, 'ZVK')
        super().save(*args, **kwargs)
