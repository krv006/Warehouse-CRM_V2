from decimal import ROUND_HALF_UP, Decimal

from django.db.models import (
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

from apps.core.models import StatusTrackedModel

MONEY = Decimal('0.01')


class ImportCostSheet(StatusTrackedModel):
    """24-to'plam: import tannarx varaqasi — tovar + logistika + bojxona.

    Uchta odam to'ldiradi (buyurtmachi — tovar, logist — logistika,
    deklarant — bojxona), shuning uchun bitta mahsulot kartasi emas,
    alohida hujjat (§5.1): "shu mahsulot, shu miqdor, shu sanada shunday
    hisoblandi" — SURATLASH. Keyingi import — yangi varaqa, eskisi tarix
    bo'lib qoladi (yopilgan varaqa tahrirlanmaydi, §7 case 11).

    Hisoblangan sonlar (§5.3) bazaga yozilmaydi — har o'qishda qayta
    hisoblanadi (21-§3.2 dagi qaror shu yerda ham amal qiladi).
    """

    class Status(TextChoices):
        DRAFT = 'draft', 'Chernovik'
        WAITING_LOGISTICS = 'waiting_logistics', 'Logist kutilmoqda'
        WAITING_CUSTOMS = 'waiting_customs', 'Deklarant kutilmoqda'
        DONE = 'done', 'Tannarx chiqdi'
        CANCELLED = 'cancelled', 'Bekor qilindi'

    # `StatusTrackedModel` faqat `status_changed_at`ni beradi — `status`
    # maydonini model o'zi e'lon qiladi (`Configuration`dagi kabi)
    status = CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    number = CharField(max_length=20, unique=True, blank=True)
    product = ForeignKey('inventory.Product', PROTECT, related_name='import_sheets')
    quantity = DecimalField(max_digits=18, decimal_places=2, default=Decimal('1'))

    # §8.3: varaqa ochilganda `CompanyProfile.vat_recoverable`dan
    # NUSXALANADI — sozlama keyin o'zgarsa yopilgan varaqaning hisobi
    # o'zgarib ketmasin (varaqa suratlash, §5.1)
    vat_recoverable = BooleanField(default=False)

    # Qaysi ish uchun ochilgani — ZVK/CFG zanjiriga ulanish (§8.7: TLD kabi
    # o'z narx oqimi bo'lgani uchun `ReplenishmentItem`ga ulanmaydi, ixtiyoriy)
    configuration = ForeignKey(
        'configurator.Configuration', SET_NULL,
        null=True, blank=True, related_name='import_sheets',
    )

    # --- A. TOVAR (buyurtmachi) ---
    currency = CharField(max_length=3, default='USD')
    goods_price = DecimalField(max_digits=18, decimal_places=2, default=Decimal('0'))
    exchange_rate = DecimalField(max_digits=18, decimal_places=4, default=Decimal('0'))
    origin_country = CharField(max_length=100, blank=True)
    goods_filled_by = ForeignKey(
        'accounts.User', SET_NULL, null=True, blank=True, related_name='+',
    )
    goods_filled_at = DateTimeField(null=True, blank=True)

    # --- B. LOGISTIKA (logist) ---
    logistics_total = DecimalField(max_digits=18, decimal_places=2, default=Decimal('0'))
    logistics_note = TextField(blank=True)
    logistics_filled_by = ForeignKey(
        'accounts.User', SET_NULL, null=True, blank=True, related_name='+',
    )
    logistics_filled_at = DateTimeField(null=True, blank=True)

    # --- C. BOJXONA (deklarant) ---
    tnved_code = CharField(max_length=20, blank=True)
    # §8.2: bojxona qiymatiga qanchasi kirishini deklarant belgilaydi
    freight_to_border = DecimalField(max_digits=18, decimal_places=2, default=Decimal('0'))
    duty_percent = DecimalField(max_digits=6, decimal_places=2, default=Decimal('0'))
    duty_amount = DecimalField(max_digits=18, decimal_places=2, default=Decimal('0'))
    excise_amount = DecimalField(max_digits=18, decimal_places=2, default=Decimal('0'))
    vat_percent = DecimalField(max_digits=5, decimal_places=2, default=Decimal('12'))
    customs_fee = DecimalField(max_digits=18, decimal_places=2, default=Decimal('0'))
    certificate_cost = DecimalField(max_digits=18, decimal_places=2, default=Decimal('0'))
    laboratory_cost = DecimalField(max_digits=18, decimal_places=2, default=Decimal('0'))
    declarant_fee = DecimalField(max_digits=18, decimal_places=2, default=Decimal('0'))
    customs_note = TextField(blank=True)
    customs_filled_by = ForeignKey(
        'accounts.User', SET_NULL, null=True, blank=True, related_name='+',
    )
    customs_filled_at = DateTimeField(null=True, blank=True)

    created_by = ForeignKey('accounts.User', SET_NULL, null=True, blank=True, related_name='+')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.number

    def save(self, *args, **kwargs):
        if not self.number:
            from apps.core.utils import next_number

            self.number = next_number(ImportCostSheet, 'IMP')
        super().save(*args, **kwargs)

    # ---- §5.3: hisoblangan xossalar — bazada saqlanmaydi ----

    @property
    def goods_uzs(self):
        """Tovar qiymati so'mda."""
        return self.goods_price * self.exchange_rate

    @property
    def customs_value(self):
        """Bojxona qiymati (BQ) = tovar + CHEGARAGACHA yetkazish."""
        return self.goods_uzs + self.freight_to_border

    @property
    def duty(self):
        """Boj — qo'lda kiritilgani (`duty_amount`) foizdan USTUN turadi.

        Sabab: ba'zi stavkalar foiz emas, o'lchov birligiga qat'iy summa
        (masalan 0.5 EUR/kg) — deklarant hisoblangan summani yozadi.
        """
        if self.duty_amount:
            return self.duty_amount
        return self.customs_value * self.duty_percent / Decimal('100')

    @property
    def vat(self):
        """QQS — bazasi BQ + boj + aksiz, INVOYSDAN EMAS (§2.1 4-qadam)."""
        return (
            (self.customs_value + self.duty + self.excise_amount)
            * self.vat_percent / Decimal('100')
        )

    @property
    def vat_in_cost(self):
        """§8.3: QQS qaytariladigan bo'lsa XARAJAT emas — hisoblanadi va
        ko'rsatiladi, lekin tannarxga qo'shilmaydi."""
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
        """Jami tannarx = tovar + TO'LIQ logistika + bojxona xarajatlari."""
        return self.goods_uzs + self.logistics_total + self.customs_total

    @property
    def unit_cost(self):
        """Dona tannarx — pul sifatida faqat shu yerda ikki xonaga yaxlitlanadi.

        Oraliq qiymatlar (BQ, boj, QQS) yaxlitlanmaydi — har qadamda
        yaxlitlansa xatolar yig'ilib ketadi.
        """
        if not self.quantity:
            return Decimal('0')
        return (self.landed_total / self.quantity).quantize(MONEY, rounding=ROUND_HALF_UP)
