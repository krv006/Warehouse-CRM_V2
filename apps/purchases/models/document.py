from django.db.models import (
    CASCADE,
    SET_NULL,
    CharField,
    FileField,
    ForeignKey,
    TextChoices,
)

from apps.core.models import TimeStampedModel


class PurchaseDocument(TimeStampedModel):
    """Kirim hujjati fayli — import bilan bog'liq document qismi (TZ 2.2).

    Hujjatlar bilan Bugalter ishlaydi (TZ 8.2): shartnoma, invoys,
    bojxona deklaratsiyasi va boshqa fayllar kirimga biriktiriladi.
    """

    class Kind(TextChoices):
        CONTRACT = 'contract', 'Shartnoma'
        INVOICE = 'invoice', 'Invoys (faktura)'
        CUSTOMS = 'customs', 'Bojxona deklaratsiyasi'
        OTHER = 'other', 'Boshqa hujjat'

    purchase = ForeignKey('purchases.Purchase', CASCADE, related_name='documents')
    kind = CharField(max_length=20, choices=Kind.choices, default=Kind.OTHER)
    title = CharField(max_length=200, blank=True)
    file = FileField(upload_to='purchase-documents/')
    uploaded_by = ForeignKey(
        'accounts.User', SET_NULL, related_name='purchase_documents',
        null=True, blank=True,
    )

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.get_kind_display()} — {self.purchase}'
