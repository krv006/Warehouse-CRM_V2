from django.db.models import (
    CASCADE,
    PROTECT,
    SET_NULL,
    DecimalField,
    ForeignKey,
    PositiveIntegerField,
)

from apps.core.models import TimeStampedModel
from apps.core.utils import default_vat_percent, vat_amount_of


class ContractItem(TimeStampedModel):
    """Shartnoma qatori — sotuv narxi faqat sales va adminga ko'rinadi.

    `unit_price` — QQS'siz sof narx; QQS foizi qatorda alohida turadi
    (default 12%, imtiyozli mahsulotga 0% qo'yish mumkin).
    """

    contract = ForeignKey('sales.Contract', CASCADE, related_name='items')
    product = ForeignKey('inventory.Product', PROTECT, related_name='contract_items')
    # 12-§2 (C): bitta shartnomada bir nechta model bo'lishi mumkin — qator
    # aynan qaysi konfiguratsiyadan kelganini biladi (savdo bitta, model N ta)
    configuration = ForeignKey(
        'configurator.Configuration', SET_NULL, related_name='contract_items',
        null=True, blank=True,
    )
    quantity = PositiveIntegerField(default=1)
    unit_price = DecimalField(max_digits=18, decimal_places=2)
    vat_percent = DecimalField(
        'QQS %', max_digits=5, decimal_places=2, default=default_vat_percent,
    )

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.product} x {self.quantity}'

    @property
    def subtotal(self):
        """QQS'siz qator summasi."""
        return self.quantity * self.unit_price

    @property
    def vat_amount(self):
        return vat_amount_of(self.subtotal, self.vat_percent)

    @property
    def total_with_vat(self):
        """Qator jami — QQS bilan (chop etishdagi "Jami" ustuni)."""
        return self.subtotal + self.vat_amount
