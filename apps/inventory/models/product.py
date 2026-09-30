from django.db.models import (
    SET_NULL,
    BooleanField,
    CharField,
    DecimalField,
    ForeignKey,
    PositiveIntegerField,
    Sum,
    TextChoices,
    TextField,
)

from apps.core.models import TimeStampedModel


class Product(TimeStampedModel):
    """Ombordagi mahsulot: bazaviy model yoki uning butlovchisi (TZ 6.1).

    Katalog ma'lumotnoma hisoblanadi — TZ mahsulot omborda mavjud deb qaraydi.
    Qoldiq esa faqat Kirim va Chiqim jarayonlari orqali o'zgaradi (TZ 1-bo'lim).
    """

    class Kind(TextChoices):
        MACHINE = 'machine', 'Tayyor model'
        COMPONENT = 'component', 'Butlovchi'
        OTHER = 'other', 'Boshqa'

    sku = CharField(max_length=50, unique=True)
    name = CharField(max_length=200)
    kind = CharField(max_length=20, choices=Kind.choices, default=Kind.MACHINE)
    description = TextField(blank=True)
    # 21-§3.4: shartnoma spetsifikatsiyasida "Ед. Изм" ustuni kerak —
    # ilgari `print_form`da qattiq "dona" yozilardi
    unit = CharField(max_length=20, default='dona', blank=True)
    cost_price = DecimalField(max_digits=18, decimal_places=2, default=0)
    sale_price = DecimalField(max_digits=18, decimal_places=2, default=0)

    # TZ 7.1: qoldiq shu darajadan pastga tushsa, to'ldirish ro'yxatiga tushadi
    reorder_level = PositiveIntegerField(default=0)
    is_active = BooleanField(default=True)

    # Configurator yaratgan variant uchun: bazaviy model va tarkib imzosi (TZ 6.2)
    base_model = ForeignKey(
        'inventory.Product', SET_NULL, related_name='variants',
        null=True, blank=True,
    )
    signature = CharField(max_length=64, unique=True, null=True, blank=True)
    # 24-§3/§5.5: kod mahsulotga eslab qolinadi — keyingi importda oldindan
    # taklif qilinadi (deklarant qo'yadi, tizim taxmin qilmaydi)
    tnved_code = CharField('TN VED', max_length=20, blank=True)
    # 24-§8.1: shu mahsulot importdanmi — request_prices shu bayroqqa qarab
    # narxni buyurtmachidan (mahalliy) yoki import yo'li orqali so'raydi
    is_imported = BooleanField(default=False)
    # 28-§3: oxirgi importdan ESLAB QOLINADI — kod BOR va stavka BELGILANGAN
    # bo'lsa keyingi importda deklarant bosqichi o'tkazib yuboriladi
    # (`tnved_code` mavjudligi "stavka ham eslab qolingan" degani, chunki
    # ikkalasi bitta chaqiruvda birga yoziladi — `fill_customs`ga qarang).
    duty_percent = DecimalField(max_digits=6, decimal_places=2, default=0)
    certificate_cost = DecimalField(max_digits=18, decimal_places=2, default=0)
    laboratory_cost = DecimalField(max_digits=18, decimal_places=2, default=0)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.sku})'

    @property
    def is_variant(self):
        return self.base_model_id is not None

    @property
    def composition_signature(self):
        """Zavod tarkibining imzosi — konfiguratsiya bilan taqqoslash uchun (TZ 6.2).

        Tarkib o'zgartirilmagan bo'lsa, bazaviy modelning o'zi tayyor pozitsiya
        hisoblanadi va uning ombordagi narxi qo'llanadi.
        """
        from apps.inventory.services import configuration_signature

        specs = [(spec.component_id, spec.quantity) for spec in self.specs.all()]
        if not specs:
            return None
        return configuration_signature(self.pk, specs)

    @property
    def stock_price(self):
        """Ombordagi narx: sotuv narxi, bo'lmasa tannarx + ustama (TZ 6.2, §6-B).

        Yangi oqimda shartnoma shu narx bilan DARHOL tuziladi — buyurtmachi
        faqat tannarx kiritgan bo'lsa, `CompanyProfile.markup_percent`
        ustamasi qo'llanadi (0 bo'lsa eski xulq: tannarxning o'zi).
        """
        if self.sale_price:
            return self.sale_price
        if not self.cost_price:
            return self.cost_price
        from decimal import Decimal

        from apps.core.models import CompanyProfile

        markup = CompanyProfile.load().markup_percent
        if not markup:
            return self.cost_price
        return (
            self.cost_price * (Decimal('100') + markup) / Decimal('100')
        ).quantize(Decimal('0.01'))

    @property
    def total_stock(self):
        return self.stocks.aggregate(t=Sum('quantity'))['t'] or 0

    @property
    def is_low_stock(self):
        return self.total_stock <= self.reorder_level
