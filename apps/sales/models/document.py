from django.db.models import (
    CASCADE,
    SET_NULL,
    FileField,
    ForeignKey,
    OneToOneField,
    TextField,
)

from apps.core.models import TimeStampedModel
from apps.core.validators import document_extension_validator, validate_upload_size


class ContractDocument(TimeStampedModel):
    """Shartnomaning MATNI — 13-§1: bugalter yuklaydi va saytda tahrirlaydi.

    `body` — ko'rsatishda o'rin egallovchilar (`{{ contract.number }}` va h.k.)
    to'ldiriladigan HTML; saqlashda emas, shunda summa o'zgarsa hujjat ham
    ergashadi. `source_file` — yuklangan asl `.docx` (o'girish yo'qotishli
    bo'lgani uchun saqlanadi, o'chirilmaydi).
    """

    contract = OneToOneField('sales.Contract', CASCADE, related_name='document')
    body = TextField(blank=True)
    source_file = FileField(
        upload_to='contracts/', null=True, blank=True,
        validators=[document_extension_validator, validate_upload_size],
    )
    updated_by = ForeignKey(
        'accounts.User', SET_NULL, related_name='updated_contract_documents',
        null=True, blank=True,
    )

    def __str__(self):
        return f'{self.contract} — hujjat matni'


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
