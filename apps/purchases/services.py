from django.db.transaction import atomic
from django.utils.timezone import localdate, now
from rest_framework.exceptions import ValidationError

from apps.finance.services import record_transaction
from apps.inventory.models import StockMovement
from apps.inventory.services import apply_movement
from apps.purchases.models import Purchase

EXPENSE_CODE_BY_TYPE = {
    Purchase.Type.IMPORT: 'import',
    Purchase.Type.LOCAL: 'contract_invoice',
    Purchase.Type.USTAV: 'ustav_out',
}


@atomic
def receive_purchase(purchase, user=None):
    """Kirimni qabul qiladi: ombor qoldigi va kassa chiqimi yoziladi."""
    if purchase.status == Purchase.Status.RECEIVED:
        raise ValidationError('Bu kirim allaqachon qabul qilingan.')
    if purchase.status == Purchase.Status.CANCELLED:
        raise ValidationError('Bekor qilingan kirimni qabul qilib bo\'lmaydi.')
    if not purchase.items.exists():
        raise ValidationError('Kirim qatorlari kiritilmagan.')

    for item in purchase.items.select_related('product'):
        apply_movement(
            product=item.product,
            warehouse=purchase.warehouse,
            type=StockMovement.Type.IN,
            quantity=item.quantity,
            reason=StockMovement.Reason.PURCHASE,
            reference=purchase.number,
            user=user,
        )

    record_transaction(
        code=EXPENSE_CODE_BY_TYPE[purchase.type],
        amount=purchase.total_amount,
        occurred_at=now(),
        description=f'{purchase.number} — {purchase.get_type_display()}',
        currency=purchase.currency,
        exchange_rate=purchase.exchange_rate,
        purchase=purchase,
        user=user,
    )

    purchase.status = Purchase.Status.RECEIVED
    purchase.received_at = localdate()
    purchase.save()
    return purchase
