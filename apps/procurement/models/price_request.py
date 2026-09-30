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
    # 30-§3: MA'NOSI O'ZGARDI — invoys JAMI emas, BITTA DONANING narxi
    # (asl valyutada, `exchange_rate` bilan so'mga o'giriladi)
    goods_price = DecimalField(max_digits=18, decimal_places=2, default=Decimal('0'))
    exchange_rate = DecimalField(max_digits=18, decimal_places=4, default=Decimal('0'))
    # 30-§3: buyurtmachining IKKINCHI inputi — skotch/mashina/omborgacha
    # kabi qo'shimcha xarajatlar, JAMI (logistika kabi miqdorga bo'linadi)
    extra_costs = DecimalField(max_digits=18, decimal_places=2, default=Decimal('0'))
    cost_price = DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    answered_at = DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.product} x {self.quantity}'

    # ---- 30-§3: hisob — foydalanuvchi bergan misolga mos ----
    #
    #   1) Deklarant qismi (DONAGA):
    #      (tovar_donaga + sertifikat + laboratoriya + xizmat) × (1 + foiz/100)
    #   2) Logistika (DONAGA): logistika_jami / miqdor
    #   3) Qo'shimcha xarajatlar (DONAGA): qoshimcha_jami / miqdor
    #   TANNARX (donaga) = 1 + 2 + 3
    #
    # Eski `goods_uzs`/`customs_value`/`duty`/`vat`/`customs_total`/
    # `landed_total` — OLIB TASHLANDI: ular invoys-JAMI taxminiga
    # asoslangan edi (goods_price endi DONAGA), qolib ketsa boshqa
    # formulani aks ettirib chalg'itardi. `excise_amount`/`customs_fee`/
    # `duty_amount`/`vat_recoverable` maydonlari BAZADA qoladi (eski
    # yozuvlar tarixi buzilmasin), lekin yangi hisobda ishlatilmaydi —
    # ⚠️ QQS ham shu formulaga umuman kirmaydi (30-§3: mijoz bilan
    # "foiz" nima anglatishi — boj, QQS yoki ikkalasi — aniqlansin).

    @property
    def declarant_unit(self):
        """Deklarant qismi — DONAGA. Foiz eng oxirida, butun yig'indiga
        qo'yiladi (tovar + sertifikat + laboratoriya + xizmat);
        logistika bunga KIRMAYDI — u alohida va donaga bo'linadi."""
        base = (
            self.goods_price * self.exchange_rate
            + self.certificate_cost + self.laboratory_cost + self.declarant_fee
        )
        return base * (Decimal('100') + self.duty_percent) / Decimal('100')

    @property
    def logistics_unit(self):
        """Logistika — jami summa miqdorga bo'linadi."""
        if not self.quantity:
            return Decimal('0')
        return self.logistics_total / self.quantity

    @property
    def extra_unit(self):
        """Qo'shimcha xarajatlar — jami summa miqdorga bo'linadi."""
        if not self.quantity:
            return Decimal('0')
        return self.extra_costs / self.quantity

    @property
    def suggested_cost(self):
        """Tizim hisoblagan tannarx — buyurtmachiga TAKLIF, yakuniy qaror emas."""
        return (
            self.declarant_unit + self.logistics_unit + self.extra_unit
        ).quantize(MONEY, rounding=ROUND_HALF_UP)

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
