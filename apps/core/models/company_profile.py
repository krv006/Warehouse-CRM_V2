from django.core.exceptions import ValidationError
from django.db.models import (
    CharField,
    DecimalField,
    EmailField,
    PositiveIntegerField,
    TextField,
)

from apps.core.models.base import TimeStampedModel


class CompanyProfile(TimeStampedModel):
    """Bajaruvchi (o'z firmamiz) rekvizitlari — shartnoma chop etishda ishlatiladi.

    Tizimda bitta yozuv bo'ladi (singleton): admin to'ldiradi, qolganlar o'qiydi.
    """

    name = CharField(max_length=200, blank=True)
    inn = CharField('STIR / INN', max_length=20, blank=True)
    phone = CharField(max_length=20, blank=True)
    email = EmailField(blank=True)
    address = CharField(max_length=300, blank=True)
    bank_name = CharField(max_length=200, blank=True)
    mfo = CharField(max_length=10, blank=True)
    account_number = CharField(max_length=30, blank=True)
    director_name = CharField(max_length=200, blank=True)
    # 21-§3.4: NB2309-26 namunasidan chiqqan, shartnoma matnida kerak
    director_title = CharField(
        max_length=100, blank=True,
        help_text='Masalan: "Генерального директора" — lavozim, shartnoma sarlavhasida',
    )
    oked = CharField('ОКЭД', max_length=20, blank=True)
    registration_code = CharField('Ro\'yxatga olish kodi', max_length=50, blank=True)
    license = CharField(max_length=300, blank=True, help_text="Litsenziya raqami va kim bergani")
    city = CharField(max_length=100, blank=True, help_text='Masalan: "г. Ташкент" — shartnoma sarlavhasida')
    contract_terms = TextField(
        blank=True,
        help_text="Shartnoma chop etilganda chiqadigan standart shartlar matni",
    )
    # §11.3: shu summadan KICHIK (UZS) shartnomalar admin tasdig'isiz o'tadi.
    # 0 = chegara yo'q — har bir shartnoma adminga boradi (hozirgi tartib).
    # Solishtirish QQS BILAN total_amount ustida.
    admin_approval_threshold = DecimalField(
        max_digits=18, decimal_places=2, default=0,
        help_text="Shu summadan kichik shartnomalar admin tasdig'isiz o'tadi (QQS bilan, UZS); 0 — chegara yo'q",
    )
    # TOPSHIRIQ #2: TLD uchun ALOHIDA chegara — summalar tabiatan boshqa
    # (shartnoma o'nlab million, butlovchi yuz minglar); bitta chegara
    # ikkalasiga mos kelmaydi
    replenishment_approval_threshold = DecimalField(
        max_digits=18, decimal_places=2, default=0,
        help_text="Shu summadan kichik to'ldirish hisoblari admin tasdig'isiz o'tadi (QQS+xarajatlar bilan, UZS); 0 — chegara yo'q",
    )
    # TOPSHIRIQ #3 (SLA): kesim soatidan OLDIN kelgan ish — shu ish kunining
    # oxirigacha, KEYIN kelgani — keyingi ish kunining oxirigacha bajarilsin;
    # muddati o'tgani admin (va egasining) navbatida qizil chiqadi
    sla_cutoff_hour = PositiveIntegerField(
        default=16,
        help_text="Kesim soati: shu soatdan keyin kelgan ish keyingi ish kunidan sanaladi",
    )
    sla_working_days = PositiveIntegerField(
        default=1,
        help_text='Ishga beriladigan ish kunlari soni',
    )
    # YANGI-OQIM §6-B: buyurtmachi har doim TANNARX kiritadi; sotuv narxi
    # qo'yilmagan mahsulotda tannarx ustiga shu ustama qo'llanadi — aks holda
    # shartnoma tannarxda tuzilib, mijozga foydasiz sotilardi. 0 = ustama yo'q
    # (eski xulq: stock_price tannarxga teng bo'lib qoladi).
    markup_percent = DecimalField(
        max_digits=5, decimal_places=2, default=0,
        help_text=(
            "Sotuv narxi yo'q mahsulotda tannarx ustiga avtomatik ustama (%); "
            "0 — ustama yo'q, tannarx ishlatiladi"
        ),
    )
    # §11.4: bron muddatlari (kun). 0 = muddat yo'q, qo'lda bo'shatilguncha turadi
    contract_reservation_days = PositiveIntegerField(
        default=7,
        help_text='Shartnoma chernovigi bronni necha kun ushlab turadi (0 — cheksiz)',
    )
    configuration_reservation_days = PositiveIntegerField(
        default=14,
        help_text='Konfiguratsiya chernovigi rejadagi bronni necha kun ushlab turadi (0 — cheksiz)',
    )

    def __str__(self):
        return self.name or 'Bajaruvchi rekvizitlari'

    def save(self, *args, **kwargs):
        if CompanyProfile.objects.exclude(pk=self.pk).exists():
            raise ValidationError(
                "Bajaruvchi rekvizitlari bitta bo'ladi — mavjudini tahrirlang.",
            )
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """Yagona yozuvni qaytaradi, bo'lmasa bo'sh holda ochadi."""
        profile = cls.objects.first()
        if profile is None:
            profile = cls.objects.create()
        return profile
