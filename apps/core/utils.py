from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.utils.timezone import localdate

GREEN = 'green'
YELLOW = 'yellow'
RED = 'red'
GREY = 'grey'

# TZ 5.3: oxirgi 10 kun qizil, muddatning oxirgi uchdan biri sariq
# (90 kunlik shartnomada: yashil 90-31, sariq 30-11, qizil 10-0)
RED_ZONE_DAYS = 10
YELLOW_ZONE_RATIO = 1 / 3


def parse_amount(value, field='amount'):
    """Front yuborgan summani (satr, int, float) Decimal ga o'giradi.

    Bo'sh qiymat (None, '') — None qaytadi (chaqiruvchi default ishlatadi).
    Noto'g'ri format 500 emas, 400 bo'lishi kerak — ValidationError ko'tariladi.
    """
    from rest_framework.exceptions import ValidationError

    if value is None or value == '':
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValidationError({field: "Summa noto'g'ri formatda — son yuboring."})


def default_vat_percent():
    """Sotuv qatori uchun standart QQS foizi (sozlamadan, default 12%)."""
    return Decimal(str(getattr(settings, 'DEFAULT_VAT_PERCENT', 12)))


def vat_amount_of(subtotal, percent):
    """Qator QQS summasi: sof narxdan foiz bilan hisoblanadi."""
    return (
        Decimal(subtotal or 0) * Decimal(percent or 0) / Decimal('100')
    ).quantize(Decimal('0.01'))


def deadline_color(days_left, term_days):
    """Muddatga qarab rang: yashil -> sariq -> oxirgi 10 kun qizil."""
    if days_left is None or not term_days:
        return GREY
    if days_left <= RED_ZONE_DAYS:
        return RED
    if days_left <= term_days * YELLOW_ZONE_RATIO:
        return YELLOW
    return GREEN


def deadline_progress(start_date, term_days, today=None):
    """Line chart uchun kunlik sanoq ma'lumotlari."""
    if not start_date or not term_days:
        return {
            'start_date': start_date,
            'term_days': term_days,
            'deadline': None,
            'days_left': None,
            'days_passed': None,
            'color': GREY,
            'is_overdue': False,
            'points': [],
        }

    today = today or localdate()
    deadline = start_date + timedelta(days=term_days)
    days_left = (deadline - today).days
    days_passed = max((today - start_date).days, 0)

    points = [
        {
            'date': start_date + timedelta(days=day),
            'days_left': term_days - day,
            'color': deadline_color(term_days - day, term_days),
        }
        for day in range(term_days + 1)
    ]

    return {
        'start_date': start_date,
        'term_days': term_days,
        'deadline': deadline,
        'days_left': days_left,
        'days_passed': days_passed,
        'color': deadline_color(days_left, term_days),
        'is_overdue': days_left < 0,
        'points': points,
    }


# ------------------------------------------------- SLA — ish kuni hisobi (#3)

def next_working_day(day):
    """Keyingi ish kuni (shanba/yakshanba sanalmaydi)."""
    day = day + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def sla_deadline(entered_at, cutoff_hour, working_days):
    """Ish qachongacha bajarilishi kerak (sana, shu kunning oxiri deb o'qiladi).

    Kesim soatidan OLDIN kelgan (va ish kuniga tushgan) ish — shu kunning
    oxirigacha; KEYIN kelgani yoki dam olish kuniga tushgani — keyingi ish
    kunidan sanaladi. `working_days` > 1 bo'lsa qo'shimcha ish kunlari
    qo'shiladi. Misollar (cutoff=16, days=1):
      Du 12:00 -> Du oxiri (Se kuni qizil)
      Du 17:00 -> Se oxiri (Cho kuni qizil)
      Ju 17:00 -> Du oxiri (Se kuni qizil — shanba/yakshanba o'tkaziladi)
    """
    from django.utils.timezone import localtime

    moment = localtime(entered_at)
    day = moment.date()
    if day.weekday() >= 5 or moment.hour >= cutoff_hour:
        day = next_working_day(day)
    for _ in range(max(working_days, 1) - 1):
        day = next_working_day(day)
    return day


def working_days_since(start_date, today=None):
    """`start_date` dan keyin nechta to'liq ish kuni o'tgani (bugungi kun bilan)."""
    today = today or localdate()
    days = 0
    day = start_date
    while day < today:
        day += timedelta(days=1)
        if day.weekday() < 5:
            days += 1
    return days


def next_number(model, prefix, width=5):
    """Hujjat raqamini ketma-ket generatsiya qiladi: PREFIX-00001."""
    last = model.objects.order_by('-id').first()
    seq = (last.id + 1) if last else 1
    return f'{prefix}-{seq:0{width}d}'
