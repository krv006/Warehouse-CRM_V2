from django.db.models import (
    CASCADE,
    SET_NULL,
    BooleanField,
    ForeignKey,
    OneToOneField,
    TextField,
)

from apps.core.models import TimeStampedModel


class ContractDocument(TimeStampedModel):
    """Shartnomaning MATNI — 21-§3.2: shablon + avtomatik bloklar.

    `body` — sales/admin (yoki bugalter) yozgan HTML, YAGONA manba —
    ichida `{{ key }}` **saqlanib turadi**, o'rin egallovchilar faqat
    KO'RISHDA to'ldiriladi (`render_contract_document`), shuning uchun
    summa o'zgarsa hujjat matni ergashadi va "eskirdi" degan tushuncha
    umuman yo'q.

    `template` — qaysi shablondan boshlangani (faqat ma'lumot uchun):
    shablon keyin tahrirlansa yoki o'chirilsa, `body` allaqachon
    nusxalangani uchun ochiq shartnomaga ta'sir qilmaydi (`SET_NULL`).
    `has_specification`/`has_requisites` — attach paytida shablondan
    nusxalanadi, xuddi `body` kabi.
    """

    contract = OneToOneField('sales.Contract', CASCADE, related_name='document')
    template = ForeignKey(
        'sales.ContractTemplate', SET_NULL, related_name='documents',
        null=True, blank=True,
    )
    body = TextField(blank=True)
    has_specification = BooleanField(default=True)
    has_requisites = BooleanField(default=True)
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
