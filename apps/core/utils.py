from datetime import timedelta

from django.utils.timezone import localdate

GREEN = 'green'
YELLOW = 'yellow'
RED = 'red'
GREY = 'grey'

RED_ZONE_DAYS = 10
YELLOW_ZONE_RATIO = 0.3


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


def next_number(model, prefix, width=5):
    """Hujjat raqamini ketma-ket generatsiya qiladi: PREFIX-00001."""
    last = model.objects.order_by('-id').first()
    seq = (last.id + 1) if last else 1
    return f'{prefix}-{seq:0{width}d}'
