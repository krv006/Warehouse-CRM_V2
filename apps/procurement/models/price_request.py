from decimal import ROUND_HALF_UP, Decimal

from django.db.models import (
    CASCADE,
    PROTECT,
    SET_NULL,
    BooleanField,
    CharField,
    DateTimeField,
    DecimalField,
    ForeignKey,
    TextChoices,
    TextField,
)

from apps.core.models import StatusTrackedModel, TimeStampedModel
from apps.core.utils import default_vat_percent

MONEY = Decimal('0.01')


class PriceRequest(StatusTrackedModel):
    """28-§1: narx so'rovi — buyurtmachining (va import bo'lsa logist/
    deklarantning) ish joyi. `request_prices` shuni ochadi.

    `status` QATORLARDAN hisoblanadi — qo'lda qo'yiladigan yagona qiymat
    `cancelled` (28-§1 "So'rov holati" izohi). Qolgan holatlar eng ORQADAGI
    (eng kam bajarilgan) qator bosqichidan olinadi — `apps.procurement.
    services._sync_price_request_status` shu bilan shug'ullanadi.
    """

    class Status(TextChoices):
        WAITING_LOGISTICS = 'waiting_logistics', 'Logist kutilmoqda'
        WAITING_CUSTOMS = 'waiting_customs', 'Deklarant kutilmoqda'
        WAITING_SUPPLIER = 'waiting_supplier', 'Buyurtmachi kutilmoqda'
        ANSWERED = 'answered', 'Narx berildi'
        CANCELLED = 'cancelled', 'Bekor qilindi'

    status = CharField(max_length=20, choices=Status.choices, default=Status.WAITING_SUPPLIER)
    number = CharField(max_length=20, unique=True, blank=True)
    configuration = ForeignKey(
        'configurator.Configuration', CASCADE, related_name='price_requests',
    )
    created_by = ForeignKey(
        'accounts.User', SET_NULL, null=True, blank=True, related_name='+',
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.number

    def save(self, *args, **kwargs):
        if not self.number:
            from apps.core.utils import next_number

            self.number = next_number(PriceRequest, 'NRX')
        super().save(*args, **kwargs)


class PriceRequestLine(TimeStampedModel):
    """28-§1/§2: bitta mahsulot. Import bo'lsa — LOGIST va DEKLARANT ham
    shu qatorning ICHIDA hal bo'ladi, alohida hujjat ochilmaydi.

    Uch rol bir-birining raqamini ko'rmaydi (28-§2) — bu izolyatsiya
    `apps.procurement.serializers.PriceRequestLineSerializer.to_representation`
    da amalga oshadi, bu yerda faqat ma'lumot saqlanadi.
    """

    request = ForeignKey('PriceRequest', CASCADE, related_name='lines')
    product = ForeignKey('inventory.Product', PROTECT, related_name='price_request_lines')
    quantity = DecimalField(max_digits=18, decimal_places=2, default=Decimal('1'))
    # `apps.core.services._stale_info` har bir navbat manbasidan shu
    # maydonni kutadi (SLA muddati shundan sanaladi) — bu yerda hech qachon
    # yozilmaydi, shuning uchun har doim `created_at`ga tushadi (fallback,
    # xuddi status tarixi yo'q eski yozuv kabi).
    status_changed_at = DateTimeField(null=True, blank=True)

    # 28-§1: buyurtmachi belgilaydi (yoki Product.is_imported dan meros) —
    # bayroq QARORNING NATIJASI, sharti emas (§1 "tartib teskari edi" izohi)
    is_imported = BooleanField(default=False)
    # 24-§8.3 xulqi saqlanadi: varaqa (endi qator) ochilganda sozlamadan
    # NUSXALANADI — keyin o'zgarsa yopilgan qatorning hisobi o'zgarmasin
    vat_recoverable = BooleanField(default=False)

    # --- Logist (28-§2: freight_to_border ENDI shu yerda) ---
    logistics_total = DecimalField(max_digits=18, decimal_places=2, default=Decimal('0'))
    freight_to_border = DecimalField(max_digits=18, decimal_places=2, default=Decimal('0'))
    logistics_note = TextField(blank=True)
    logistics_filled_at = DateTimeField(null=True, blank=True)
    # 29-§5: yo'l xaritasida qadam kimda turgani ko'rinsin (24-to'plamdagi
    # ImportCostSheet.logistics_filled_by/customs_filled_by bilan bir xil)
    logistics_filled_by = ForeignKey(
        'accounts.User', SET_NULL, null=True, blank=True, related_name='+',
    )

    # --- Deklarant (summa emas, STAVKA — 28-§2b) ---
    tnved_code = CharField('TN VED', max_length=20, blank=True)
    duty_percent = DecimalField(max_digits=6, decimal_places=2, default=Decimal('0'))
    duty_amount = DecimalField(max_digits=18, decimal_places=2, default=Decimal('0'))
    excise_amount = DecimalField(max_digits=18, decimal_places=2, default=Decimal('0'))
    customs_fee = DecimalField(max_digits=18, decimal_places=2, default=Decimal('0'))
    certificate_cost = DecimalField(max_digits=18, decimal_places=2, default=Decimal('0'))
    laboratory_cost = DecimalField(max_digits=18, decimal_places=2, default=Decimal('0'))
    declarant_fee = DecimalField(max_digits=18, decimal_places=2, default=Decimal('0'))
    customs_note = TextField(blank=True)
    customs_filled_at = DateTimeField(null=True, blank=True)
    # 28-§3: kod+stavka Product'dan avtomatik ko'chirilgan bo'lsa True —
    # buyurtmachi shubhalansa "Deklarantga yuborish" shu bayroqni tozalaydi
    customs_auto_filled = BooleanField(default=False)
    customs_filled_by = ForeignKey(
        'accounts.User', SET_NULL, null=True, blank=True, related_name='+',
    )

    # --- Buyurtmachi (tovar va yakun) ---
    currency = CharField(max_length=3, default='USD')
    goods_price = DecimalField(max_digits=18, decimal_places=2, default=Decimal('0'))
    exchange_rate = DecimalField(max_digits=18, decimal_places=4, default=Decimal('0'))
    cost_price = DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    answered_at = DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.product} x {self.quantity}'

    # ---- 28-§2: hisob — 24-to'plamdagi bilan bir xil, faqat manba boshqa ----

    @property
    def goods_uzs(self):
        return self.goods_price * self.exchange_rate

    @property
    def customs_value(self):
        """Bojxona qiymati = tovar + LOGISTdan CHEGARAGACHA (28-§2a)."""
        return self.goods_uzs + self.freight_to_border

    @property
    def duty(self):
        if self.duty_amount:
            return self.duty_amount
        return self.customs_value * self.duty_percent / Decimal('100')

    @property
    def vat(self):
        return (
            (self.customs_value + self.duty + self.excise_amount)
            * default_vat_percent() / Decimal('100')
        )

    @property
    def vat_in_cost(self):
        return not self.vat_recoverable

    @property
    def customs_total(self):
        return (
            self.duty + self.excise_amount
            + (self.vat if self.vat_in_cost else 0)
            + self.customs_fee
            + self.certificate_cost + self.laboratory_cost + self.declarant_fee
        )

    @property
    def landed_total(self):
        return self.goods_uzs + self.logistics_total + self.customs_total

    @property
    def suggested_cost(self):
        """Tizim hisoblagan tannarx — buyurtmachiga TAKLIF, yakuniy qaror emas."""
        if not self.quantity:
            return Decimal('0')
        return (self.landed_total / self.quantity).quantize(MONEY, rounding=ROUND_HALF_UP)

    @property
    def status(self):
        """28-§1: qatorning o'z bosqichi — timestamplardan chiqariladi."""
        if self.answered_at:
            return PriceRequest.Status.ANSWERED
        if not self.is_imported:
            return PriceRequest.Status.WAITING_SUPPLIER
        if not self.logistics_filled_at:
            return PriceRequest.Status.WAITING_LOGISTICS
        if not self.customs_filled_at:
            return PriceRequest.Status.WAITING_CUSTOMS
        return PriceRequest.Status.WAITING_SUPPLIER
