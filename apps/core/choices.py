from django.db.models import TextChoices


class Currency(TextChoices):
    """Tizimdagi valyutalar. Export uchun USD/EUR/CNY oldindan qo'yilgan."""

    UZS = 'UZS', "So'm"
    USD = 'USD', 'AQSH dollari'
    EUR = 'EUR', 'Yevro'
    CNY = 'CNY', 'Yuan'


class Direction(TextChoices):
    """Kassa yo'nalishi: kirim yoki chiqim."""

    IN = 'in', 'Kirim'
    OUT = 'out', 'Chiqim'
