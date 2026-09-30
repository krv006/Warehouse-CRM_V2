from decimal import Decimal

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

    @property
    def cost(self):
        """Qator TANNARXI (27-§2) — `subtotal` bilan solishtirish uchun.

        Konfiguratsiyali qator `Configuration.cost_total`dan (donaga), oddiy
        qator `Product.cost_price`dan — ikkalasi ham shu qatorning
        `quantity`siga ko'payadi.
        """
        if self.configuration_id:
            return self.configuration.cost_total * self.quantity
        return self.product.cost_price * self.quantity

    @property
    def cost_known(self):
        """27-§2: tannarx kiritilganmi — `cost_price=0` "hali kiritilmagan" degani."""
        if self.configuration_id:
            return self.configuration.cost_known
        return bool(self.product.cost_price)

    @property
    def min_price(self):
        """Eng kam ruxsat etilgan SUBTOTAL: tannarx × (1 + eng kam ustama%) (27-§3)."""
        from apps.core.models import CompanyProfile

        percent = CompanyProfile.load().min_margin_percent
        return (self.cost * (Decimal('100') + percent) / Decimal('100')).quantize(Decimal('0.01'))

    @property
    def margin_state(self):
        """27-§2/§3: 'unknown' | 'below_cost' | 'below_min' | 'ok'.

        QQS'siz `subtotal` bilan solishtiriladi — QQS marja emas, davlatga
        o'tadi. Narx tannarxga TENG bo'lsa ham qizil (`<=`, talab shunday).
        """
        from apps.core.choices import Currency

        # 27-§5 case 12: shartnoma UZS bo'lmasa tekshiruv o'tkazib yuboriladi
        # — tannarx so'mda, kurs esa shartnomada yo'q, taxminiy solishtirish
        # yolg'on ogohlantirish berardi.
        if self.contract_id and self.contract.currency != Currency.UZS:
            return 'unknown'
        if not self.cost_known:
            return 'unknown'
        if self.subtotal <= self.cost:
            return 'below_cost'
        if self.subtotal < self.min_price:
            return 'below_min'
        return 'ok'
