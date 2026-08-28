from django.db.models import Sum
from django.db.transaction import atomic

from apps.inventory.models import Stock, StockMovement


def main_warehouse():
    """Tizimdagi yagona ombor — biznesda bitta ombor bor (filial yo'q).

    Ombor hali ochilmagan bo'lsa "Asosiy ombor" yaratib qaytaradi, shuning
    uchun jarayonlar hech qachon "ombor tanlanmagan" deb to'xtab qolmaydi.
    """
    from apps.inventory.models import Warehouse

    warehouse = Warehouse.objects.filter(is_active=True).order_by('id').first()
    if warehouse is None:
        warehouse = Warehouse.objects.first()
    if warehouse is None:
        warehouse = Warehouse.objects.create(name='Asosiy ombor')
    return warehouse


def available_quantity(product, warehouse=None):
    """Mahsulotning ombordagi (yoki barcha omborlardagi) qoldigi."""
    stocks = Stock.objects.filter(product=product)
    if warehouse is not None:
        stocks = stocks.filter(warehouse=warehouse)
    return stocks.aggregate(t=Sum('quantity'))['t'] or 0


@atomic
def apply_movement(*, product, warehouse, type, quantity,
                   reason=StockMovement.Reason.MANUAL, reference='', note='', user=None):
    """Harakatni yozib, ombor qoldigini yangilaydi."""
    movement = StockMovement.objects.create(
        product=product,
        warehouse=warehouse,
        type=type,
        reason=reason,
        quantity=quantity,
        reference=reference,
        note=note,
        created_by=user,
    )
    sync_stock(movement)
    return movement


@atomic
def sync_stock(movement):
    """StockMovement bo'yicha Stock qoldigini hisoblaydi."""
    stock, _ = Stock.objects.select_for_update().get_or_create(
        product=movement.product,
        warehouse=movement.warehouse,
    )
    if movement.type == StockMovement.Type.IN:
        stock.quantity += movement.quantity
    elif movement.type == StockMovement.Type.OUT:
        stock.quantity -= movement.quantity
    else:  # ADJUST — quantity yakuniy qoldiqni bildiradi
        stock.quantity = movement.quantity
    stock.save()
    return stock


def configuration_signature(base_product_id, items):
    """Konfiguratsiya tarkibining takrorlanmas imzosi.

    Bir xil bazaviy model + bir xil butlovchilar (miqdori bilan) doim
    bir xil imzo beradi — shu orqali "bunday variant avval bo'lganmi"
    degan taqqoslash bajariladi (TZ 6.2).
    """
    from hashlib import sha256

    parts = sorted(f'{component_id}x{int(quantity)}' for component_id, quantity in items)
    raw = f'{base_product_id}|' + '|'.join(parts)
    return sha256(raw.encode('utf-8')).hexdigest()[:40]


def create_product_from_order(*, name, sku='', kind=None, cost_price=0):
    """Buyurtma qilingan yangi mahsulotni katalogga qo'shadi (TZ 7).

    Buyurtmachi to'ldirish hisobiga hali bazada yo'q tovarni yozganda,
    o'sha tovar shu yerda mahsulot sifatida yaratiladi. Alohida "mahsulot
    qo'shish" oynasi yo'q — buyurtma qilishning o'zi mahsulot qo'shishdir.
    """
    from apps.core.utils import next_number
    from apps.inventory.models import Product

    name = (name or '').strip()
    sku = (sku or '').strip()
    if not name and not sku:
        raise ValueError('Mahsulot nomi yoki SKU kerak.')

    existing = None
    if sku:
        existing = Product.objects.filter(sku=sku).first()
    if not existing and name:
        existing = Product.objects.filter(name__iexact=name).first()
    if existing:
        return existing

    return Product.objects.create(
        sku=sku or next_number(Product, 'MAH'),
        name=name or sku,
        kind=kind or Product.Kind.COMPONENT,
        cost_price=cost_price or 0,
    )
