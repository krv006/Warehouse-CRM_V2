from apps.core.choices import Direction
from apps.finance.models import CashCategory, CashTransaction

# TZ: kirim 3 xil, chiqim esa import, faktura va kichik xarajatlardan iborat
DEFAULT_CATEGORIES = [
    ('sale', 'Mahsulot sotuvidan', Direction.IN),
    ('ustav_in', 'Ustav kapitali', Direction.IN),
    ('loan', 'Qarz olish', Direction.IN),
    ('import', 'Import xarajati', Direction.OUT),
    ('contract_invoice', 'Shartnoma fakturasi (UZB ichidan)', Direction.OUT),
    ('ustav_out', 'Ustav kapitalidan xarajat', Direction.OUT),
    ('salary', 'Oylik', Direction.OUT),
    ('rent', 'Arenda', Direction.OUT),
    ('meal', 'Obed', Direction.OUT),
    ('loan_repay', 'Qarzni qaytarish', Direction.OUT),
    ('other', 'Boshqa xarajat', Direction.OUT),
]


def ensure_default_categories():
    """Tizim kategoriyalarini yaratadi (mavjudlarini tegmaydi)."""
    created = []
    for code, name, direction in DEFAULT_CATEGORIES:
        category, is_new = CashCategory.objects.get_or_create(
            code=code,
            defaults={'name': name, 'direction': direction, 'is_system': True},
        )
        if is_new:
            created.append(category)
    return created


def get_category(code):
    """Kod bo'yicha kategoriya, kerak bo'lsa yaratadi."""
    category = CashCategory.objects.filter(code=code).first()
    if category:
        return category
    ensure_default_categories()
    return CashCategory.objects.filter(code=code).first()


def record_transaction(*, code, amount, occurred_at, description='', currency=None,
                       exchange_rate=1, contract=None, purchase=None, loan=None,
                       expense_request=None, user=None, approved_by=None):
    """Kassaga kirim yoki chiqim yozuvini qo'shadi."""
    category = get_category(code)
    fields = {
        'category': category,
        'amount': amount,
        'occurred_at': occurred_at,
        'description': description,
        'exchange_rate': exchange_rate,
        'contract': contract,
        'purchase': purchase,
        'loan': loan,
        'expense_request': expense_request,
        'created_by': user,
        'approved_by': approved_by,
    }
    if currency:
        fields['currency'] = currency
    return CashTransaction.objects.create(**fields)
