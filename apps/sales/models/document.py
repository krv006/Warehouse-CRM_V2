from django.db.models import (
    CASCADE,
    SET_NULL,
    CharField,
    DateTimeField,
    DecimalField,
    FileField,
    ForeignKey,
    OneToOneField,
    PositiveIntegerField,
    TextField,
)

from apps.core.models import TimeStampedModel
from apps.core.validators import document_extension_validator, validate_upload_size


class ContractDocument(TimeStampedModel):
    """Shartnomaning MATNI — 13-§1: bugalter `.docx` yuklaydi, sayt ko'rsatadi.

    `body` — KO'RISH uchun HTML (mammoth bilan qayta o'girilgan — o'qish
    rejimi, saytda tahrirlanmaydi). `source_file` — yuklangan asl `.docx`
    (o'girish yo'qotishli bo'lgani uchun saqlanadi, o'chirilmaydi) —
    15-§3: bugalter uni qaytadan yuklab olishi kerak, `source_uploaded_at`
    shu faylning yuklangan vaqti (`updated_at` boshqa saqlashda ham
    o'zgaradi — fayl vaqti alohida).

    15-§A (Didoxga aynan o'sha holicha ketishi kerak — piksel-piksel):
    `source_file` ASL hujjat — Collabora Online (WOPI) orqali brauzerda
    to'g'ridan-to'g'ri tahrirlanadi. O'rin egallovchilar YUKLASHDA
    to'ldiriladi (`docxtpl`) — fayl shundan keyin statik, summa o'zgarsa
    bugalter qayta yuklaydi. `docx_version` — WOPI `Version`, har
    `PutFile`da +1. `wopi_lock` / `wopi_lock_expires_at` — Collabora
    tahrir sessiyasi qulfi (WOPI LOCK/UNLOCK/REFRESH_LOCK spetsifikatsiyasi).

    QOLGAN-ISHLAR-2 §3: `rendered_total` — shablon TO'LDIRILGAN paytdagi
    shartnoma summasi (`upload_contract_document` yozadi). Keyin summa
    o'zgarsa (partiya, yangi model, detach) fayldagi raqam eskirib qoladi —
    `is_stale` shuni bildiradi, front qizil ogohlantirish chizadi.
    """

    contract = OneToOneField('sales.Contract', CASCADE, related_name='document')
    body = TextField(blank=True)
    source_file = FileField(
        upload_to='contracts/', null=True, blank=True,
        validators=[document_extension_validator, validate_upload_size],
    )
    source_uploaded_at = DateTimeField(null=True, blank=True)
    rendered_total = DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    docx_version = PositiveIntegerField(default=0)
    wopi_lock = CharField(max_length=255, blank=True, default='')
    wopi_lock_expires_at = DateTimeField(null=True, blank=True)
    updated_by = ForeignKey(
        'accounts.User', SET_NULL, related_name='updated_contract_documents',
        null=True, blank=True,
    )

    def __str__(self):
        return f'{self.contract} — hujjat matni'

    @property
    def wopi_lock_active(self):
        from django.utils.timezone import now

        return bool(
            self.wopi_lock and self.wopi_lock_expires_at
            and self.wopi_lock_expires_at > now(),
        )

    @property
    def is_stale(self):
        """QOLGAN-ISHLAR-2 §3: fayl to'ldirilgandan keyin summa o'zgarganmi."""
        return bool(
            self.rendered_total is not None
            and self.rendered_total != self.contract.total_amount,
        )


class ContractDocumentVersion(TimeStampedModel):
    """Har saqlash — yangi versiya. Hujjat huquqiy, tarixi kerak (13-§1)."""

    document = ForeignKey('sales.ContractDocument', CASCADE, related_name='versions')
    body = TextField()
    created_by = ForeignKey(
        'accounts.User', SET_NULL, related_name='contract_document_versions',
        null=True, blank=True,
    )

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.document} — versiya #{self.pk}'
