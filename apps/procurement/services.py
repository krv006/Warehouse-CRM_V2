from django.db.transaction import atomic
from django.utils.timezone import localdate, now
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.core.models import Notification
from apps.finance.models import Loan
from apps.finance.services import cash_balance, record_transaction
from apps.inventory.models import Product, StockMovement
from apps.inventory.services import apply_movement
from apps.procurement.models import (
    DEBT_TERM_DAYS,
    Replenishment,
    ReplenishmentApproval,
    ReplenishmentEvent,
    ReplenishmentItem,
)


def _require(user, *, supplier=False, bugalter=False, admin=False):
    if not user or not user.is_authenticated:
        raise PermissionDenied('Avtorizatsiya talab qilinadi.')
    if user.is_admin:
        return
    if supplier and user.is_supplier:
        return
    if bugalter and user.is_bugalter:
        return
    if admin:
        raise PermissionDenied('Bu bosqichni faqat admin tasdiqlaydi.')
    raise PermissionDenied('Bu amal uchun ruxsat yo\'q.')


def low_stock_products(warehouse=None):
    """Qoldig'i tugagan yoki reorder darajasidan pastga tushgan mahsulotlar (TZ 7.1).

    Omborda hali umuman yozuvi yo'q mahsulot ham ro'yxatga tushadi — qoldig'i 0.
    Har bir mahsulotga `current_stock` qiymati biriktiriladi.
    """
    products = Product.objects.filter(is_active=True).prefetch_related('stocks')
    found = []
    for product in products:
        if warehouse is None:
            quantity = product.total_stock
        else:
            quantity = sum(
                stock.quantity for stock in product.stocks.all()
                if stock.warehouse_id == warehouse.id
            )
        if quantity <= product.reorder_level:
            product.current_stock = quantity
            found.append(product)
    return found


@atomic
def build_from_low_stock(warehouse, user, supplier=''):
    """Yetishmayotgan mahsulotlar ro'yxatidan to'ldirish buyurtmasini shakllantiradi."""
    _require(user, supplier=True)
    products = low_stock_products(warehouse)
    if not products:
        raise ValidationError('Omborda yetishmayotgan mahsulot topilmadi.')

    replenishment = Replenishment.objects.create(
        warehouse=warehouse,
        supplier=supplier,
        created_by=user,
    )
    for product in products:
        needed = max(product.reorder_level - product.current_stock, 1)
        ReplenishmentItem.objects.create(
            replenishment=replenishment,
            product=product,
            quantity=needed,
            unit_price=product.cost_price,
        )
    return replenishment


@atomic
def submit(replenishment, user):
    """Buyurtmachi hisobni bugalter tekshiruviga yuboradi."""
    _require(user, supplier=True)
    if replenishment.status not in {Replenishment.Status.DRAFT, Replenishment.Status.REJECTED}:
        raise ValidationError('Faqat qoralama holatidagi hisob yuboriladi.')
    if not replenishment.items.exists():
        raise ValidationError('Hisobda birorta ham mahsulot yo\'q.')

    no_price = [item for item in replenishment.items.all() if item.needs_price]
    if no_price:
        raise ValidationError({
            'items': [item.product.name for item in no_price],
            'detail': 'Narxi kiritilmagan pozitsiyalar bor.',
        })

    replenishment.status = Replenishment.Status.PENDING_BUGALTER
    replenishment.save()
    return replenishment


@atomic
def approve(replenishment, user, comment=''):
    """Bugalter tekshiradi -> admin tasdiqlaydi (TZ 9)."""
    if replenishment.status == Replenishment.Status.PENDING_BUGALTER:
        _require(user, bugalter=True)
        step = ReplenishmentApproval.Step.BUGALTER
        replenishment.status = Replenishment.Status.PENDING_ADMIN
    elif replenishment.status == Replenishment.Status.PENDING_ADMIN:
        _require(user, admin=True)
        step = ReplenishmentApproval.Step.ADMIN
        replenishment.status = Replenishment.Status.APPROVED
    else:
        raise ValidationError('Hisob tasdiqlash bosqichida emas.')

    replenishment.save()
    ReplenishmentApproval.objects.create(
        replenishment=replenishment,
        step=step,
        decision=ReplenishmentApproval.Decision.APPROVED,
        comment=comment,
        decided_by=user,
    )
    return replenishment


@atomic
def reject(replenishment, user, comment=''):
    """Bugalter yoki admin hisobni qaytaradi."""
    if replenishment.status == Replenishment.Status.PENDING_BUGALTER:
        _require(user, bugalter=True)
        step = ReplenishmentApproval.Step.BUGALTER
    elif replenishment.status == Replenishment.Status.PENDING_ADMIN:
        _require(user, admin=True)
        step = ReplenishmentApproval.Step.ADMIN
    else:
        raise ValidationError('Hisob tasdiqlash bosqichida emas.')

    replenishment.status = Replenishment.Status.REJECTED
    replenishment.save()
    ReplenishmentApproval.objects.create(
        replenishment=replenishment,
        step=step,
        decision=ReplenishmentApproval.Decision.REJECTED,
        comment=comment,
        decided_by=user,
    )
    Notification.objects.create(
        user=replenishment.created_by,
        title=f'{replenishment.number}: hisob qaytarildi',
        message=comment,
        level=Notification.Level.WARNING,
        entity='Replenishment',
        object_id=str(replenishment.pk),
    )
    return replenishment


@atomic
def pay(replenishment, user, *, debt_amount=None):
    """Tasdiqlangan hisobni to'lash. Pul yetmasa — farqi qarzga o'tadi (TZ 7.1).

    debt_amount berilmasa, kassadagi mavjud pulga qarab avtomatik hisoblanadi.
    """
    _require(user, bugalter=True)
    if replenishment.status != Replenishment.Status.APPROVED:
        raise ValidationError('Avval hisob admin tomonidan tasdiqlanishi kerak.')

    total = replenishment.total_amount
    available = cash_balance()
    debt_amount = replenishment.shortfall if debt_amount is None else debt_amount
    debt_amount = min(max(debt_amount, 0), total)
    cash_part = total - debt_amount

    if cash_part > available:
        raise ValidationError({
            'detail': 'Kassada yetarli pul yo\'q.',
            'total': total,
            'cash_available': available,
            'suggested_debt': total - available,
        })

    if cash_part:
        record_transaction(
            code='import' if replenishment.supplier else 'other',
            amount=cash_part,
            occurred_at=now(),
            description=f'{replenishment.number} — omborni to\'ldirish',
            currency=replenishment.currency,
            user=user,
            approved_by=user,
        )

    if debt_amount:
        deadline = replenishment.default_debt_deadline
        loan = Loan.objects.create(
            lender_name=replenishment.supplier or 'Ta\'minotchi',
            amount=debt_amount,
            currency=replenishment.currency,
            taken_at=localdate(),
            deadline=deadline,
            source=Loan.Source.SUPPLIER,
            note=f'{replenishment.number} bo\'yicha qarz',
            created_by=user,
        )
        record_transaction(
            code='loan',
            amount=debt_amount,
            occurred_at=now(),
            description=f'{replenishment.number} — qarzga o\'tqazildi',
            currency=replenishment.currency,
            loan=loan,
            user=user,
        )
        replenishment.debt = loan
        Notification.objects.create(
            title=f'{replenishment.number}: {debt_amount} qarzga o\'tqazildi',
            message=f'Muddat: {deadline}',
            level=Notification.Level.WARNING,
            entity='Replenishment',
            object_id=str(replenishment.pk),
            due_date=deadline,
        )

    replenishment.paid_amount = cash_part
    replenishment.status = Replenishment.Status.ORDERED
    replenishment.save()

    ReplenishmentEvent.objects.create(
        replenishment=replenishment,
        stage=ReplenishmentEvent.Stage.ORDERED,
        comment='To\'lov amalga oshirildi, buyurtma berildi',
        happened_at=now(),
        created_by=user,
    )
    return replenishment


@atomic
def add_event(replenishment, user, *, stage, comment='', happened_at=None):
    """Yetkazib berish bosqichini qayd etadi (bojxona va h.k. — TZ 7.3)."""
    _require(user, supplier=True, bugalter=True)
    event = ReplenishmentEvent.objects.create(
        replenishment=replenishment,
        stage=stage,
        comment=comment,
        happened_at=happened_at or now(),
        created_by=user,
    )

    stage_to_status = {
        ReplenishmentEvent.Stage.SHIPPED: Replenishment.Status.IN_TRANSIT,
        ReplenishmentEvent.Stage.CUSTOMS: Replenishment.Status.CUSTOMS,
        ReplenishmentEvent.Stage.CLEARED: Replenishment.Status.IN_TRANSIT,
    }
    new_status = stage_to_status.get(stage)
    if new_status and replenishment.status not in {
        Replenishment.Status.DELIVERED, Replenishment.Status.CANCELLED,
    }:
        replenishment.status = new_status
        replenishment.save()
    return event


@atomic
def receive(replenishment, user):
    """Mahsulot omborga kirim qilinadi; qarz muddati shu kundan hisoblanadi (TZ 7.2)."""
    _require(user, supplier=True, bugalter=True)
    if replenishment.status == Replenishment.Status.DELIVERED:
        raise ValidationError('Bu hisob allaqachon omborga kirim qilingan.')
    if replenishment.status in {Replenishment.Status.DRAFT, Replenishment.Status.PENDING_BUGALTER,
                                Replenishment.Status.PENDING_ADMIN, Replenishment.Status.REJECTED}:
        raise ValidationError('Avval hisob tasdiqlanib, to\'lov qilinishi kerak.')

    for item in replenishment.items.select_related('product'):
        apply_movement(
            product=item.product,
            warehouse=replenishment.warehouse,
            type=StockMovement.Type.IN,
            quantity=item.quantity,
            reason=StockMovement.Reason.PURCHASE,
            reference=replenishment.number,
            user=user,
        )

    today = localdate()
    replenishment.delivered_at = today
    replenishment.status = Replenishment.Status.DELIVERED

    # Qarz sanog'i mahsulot kelgan kundan boshlanadi
    if replenishment.debt:
        from datetime import timedelta

        replenishment.debt.taken_at = today
        replenishment.debt.deadline = today + timedelta(days=DEBT_TERM_DAYS)
        replenishment.debt.save()

    replenishment.save()
    ReplenishmentEvent.objects.create(
        replenishment=replenishment,
        stage=ReplenishmentEvent.Stage.ARRIVED,
        comment='Omborga kirim qilindi',
        happened_at=now(),
        created_by=user,
    )
    return replenishment
