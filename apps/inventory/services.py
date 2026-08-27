from django.db.models import Sum
from django.db.transaction import atomic

from apps.inventory.models import Stock, StockMovement


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
