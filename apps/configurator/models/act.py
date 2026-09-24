from django.db.models import (
    SET_NULL,
    BooleanField,
    CharField,
    DateField,
    FileField,
    ForeignKey,
    TextChoices,
    TextField,
)

from apps.core.models import StatusTrackedModel
from apps.core.validators import document_extension_validator, validate_upload_size


class Act(StatusTrackedModel):
    """ACT — model tarkibini o'zgartirishga asos bo'ladigan hujjat. Sales bosqichida kiritiladi.

    20-§3: ACT — tarkib o'zgarishining MOLIYAVIY asosi (modify rejimida
    yechib olingan butlovchilar narxi bilan omborga qaytadi, qo'shilgani
    chiqadi — ombor qiymati va tannarx o'zgaradi), shuning uchun uni
    yozadigan odam (engineer) bilan javob beradigan odam (bugalter) bir
    xil bo'lmasligi kerak. `status` shu tasdiq zanjirini yuritadi —
    savdoda ACT bitta (14-§7), demak bitta ACT = butun savdo uchun bitta
    qaror. `ship_contract` `approved` bo'lmagan ACT bilan molni chiqarmaydi.
    `status_changed_at` (`StatusTrackedModel`) — roadmap SLA shundan
    hisoblaydi ("bugalter necha kundan buyon ushlab turibdi").
    """

    class Status(TextChoices):
        DRAFT = 'draft', 'Qoralama'
        PENDING_BUGALTER = 'pending_bugalter', "Bugalter tasdig'i kutilmoqda"
        APPROVED = 'approved', 'Tasdiqlandi'
        REJECTED = 'rejected', 'Qaytarildi'

    number = CharField(max_length=50, unique=True)
    title = CharField(max_length=200)
    description = TextField(blank=True)
    issued_at = DateField()
    file = FileField(
        upload_to='acts/', null=True, blank=True,
        validators=[document_extension_validator, validate_upload_size],
    )
    status = CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    is_active = BooleanField(default=True)
    created_by = ForeignKey(
        'accounts.User', SET_NULL, related_name='acts',
        null=True, blank=True,
    )

    def __str__(self):
        return f'{self.number} — {self.title}'
