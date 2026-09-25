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


# ---------------------------------------------------------------------------
# 21-§3.4: summa so'z bilan — shartnoma spetsifikatsiyasida kerak
# ("Семьдесят семь миллионов … сум и 10 тийин"). Ikki til: shablon
# `language`iga qarab (ru — grammatik jins bilan, uz — jinssiz).
# ---------------------------------------------------------------------------

_RU_ONES = ['', 'один', 'два', 'три', 'четыре', 'пять', 'шесть', 'семь', 'восемь', 'девять']
_RU_ONES_FEM = ['', 'одна', 'две', 'три', 'четыре', 'пять', 'шесть', 'семь', 'восемь', 'девять']
_RU_TEENS = [
    'десять', 'одиннадцать', 'двенадцать', 'тринадцать', 'четырнадцать',
    'пятнадцать', 'шестнадцать', 'семнадцать', 'восемнадцать', 'девятнадцать',
]
_RU_TENS = [
    '', '', 'двадцать', 'тридцать', 'сорок', 'пятьдесят',
    'шестьдесят', 'семьдесят', 'восемьдесят', 'девяносто',
]
_RU_HUNDREDS = [
    '', 'сто', 'двести', 'триста', 'четыреста', 'пятьсот',
    'шестьсот', 'семьсот', 'восемьсот', 'девятьсот',
]
# (birlik, 2-4 uchun, 5+/11-19 uchun, ayollik jinsimi)
_RU_SCALE = [
    ('', '', '', False),
    ('тысяча', 'тысячи', 'тысяч', True),
    ('миллион', 'миллиона', 'миллионов', False),
    ('миллиард', 'миллиарда', 'миллиардов', False),
]


def _ru_plural(n, one, few, many):
    n = n % 100
    if 11 <= n <= 19:
        return many
    tail = n % 10
    if tail == 1:
        return one
    if 2 <= tail <= 4:
        return few
    return many


def _ru_group_words(n, feminine=False):
    words = []
    hundreds, rem = divmod(n, 100)
    if hundreds:
        words.append(_RU_HUNDREDS[hundreds])
    if 10 <= rem < 20:
        words.append(_RU_TEENS[rem - 10])
    else:
        tens, ones = divmod(rem, 10)
        if tens:
            words.append(_RU_TENS[tens])
        if ones:
            words.append((_RU_ONES_FEM if feminine else _RU_ONES)[ones])
    return words


def _number_to_words_ru(n):
    if n == 0:
        return 'ноль'
    groups = []
    temp = n
    while temp > 0:
        temp, rem = divmod(temp, 1000)
        groups.append(rem)
    words = []
    for i in range(len(groups) - 1, -1, -1):
        group = groups[i]
        if group == 0:
            continue
        words += _ru_group_words(group, feminine=(i == 1))
        if i > 0:
            one, few, many, _fem = _RU_SCALE[i]
            words.append(_ru_plural(group, one, few, many))
    return ' '.join(words)


_UZ_ONES = ['', 'bir', 'ikki', 'uch', "to'rt", 'besh', 'olti', 'yetti', 'sakkiz', "to'qqiz"]
_UZ_TENS = ['', "o'n", 'yigirma', "o'ttiz", 'qirq', 'ellik', 'oltmish', 'yetmish', 'sakson', "to'qson"]
_UZ_SCALE = ['', 'ming', 'million', 'milliard']


def _uz_group_words(n):
    words = []
    hundreds, rem = divmod(n, 100)
    if hundreds:
        if hundreds > 1:
            words.append(_UZ_ONES[hundreds])
        words.append('yuz')
    tens, ones = divmod(rem, 10)
    if tens:
        words.append(_UZ_TENS[tens])
    if ones:
        words.append(_UZ_ONES[ones])
    return words


def _number_to_words_uz(n):
    if n == 0:
        return 'nol'
    groups = []
    temp = n
    while temp > 0:
        temp, rem = divmod(temp, 1000)
        groups.append(rem)
    words = []
    for i in range(len(groups) - 1, -1, -1):
        group = groups[i]
        if group == 0:
            continue
        words += _uz_group_words(group)
        if i > 0:
            words.append(_UZ_SCALE[i])
    return ' '.join(words)


def amount_in_words(amount, language='ru'):
    """Summani so'z bilan yozadi — UZS, butun qismi + tiyin (21-§3.4).

    `language` shablonning `ContractTemplate.language`sidan keladi —
    ruscha shablonda ruscha (grammatik jins bilan), o'zbekchada o'zbekcha.
    """
    amount = Decimal(amount or 0).quantize(Decimal('0.01'))
    whole = int(amount)
    tiyin = int((amount - whole) * 100)

    if language == 'uz':
        words = _number_to_words_uz(whole)
        words = words[0].upper() + words[1:]
        return f"{words} so'm va {tiyin:02d} tiyin"

    words = _number_to_words_ru(whole)
    words = words[0].upper() + words[1:]
    return f'{words} сум и {tiyin:02d} тийин'
