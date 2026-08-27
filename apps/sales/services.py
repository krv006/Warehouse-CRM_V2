from django.db.transaction import atomic
from django.utils.timezone import now
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.core.models import Notification
from apps.finance.services import record_transaction
from apps.sales.models import Contract, ContractApproval, ContractPayment


def _require_role(user, *, bugalter=False, admin=False, sales=False):
    if not user or not user.is_authenticated:
        raise PermissionDenied('Avtorizatsiya talab qilinadi.')
    if user.is_admin:
        return
    if bugalter and user.is_bugalter:
        return
    if sales and user.is_sales:
        return
    if admin:
        raise PermissionDenied('Bu bosqichni faqat admin tasdiqlaydi.')
    raise PermissionDenied('Bu amal uchun ruxsat yo\'q.')


@atomic
def submit_contract(contract, user):
    """Sales shartnomani bugalter tasdig'iga yuboradi."""
    _require_role(user, sales=True)
    if contract.status != Contract.Status.DRAFT:
        raise ValidationError('Faqat qoralama shartnoma yuboriladi.')
    if not contract.items.exists():
        raise ValidationError('Shartnoma qatorlari kiritilmagan.')
    contract.status = Contract.Status.PENDING_BUGALTER
    contract.save()
    return contract


@atomic
def approve_contract(contract, user, comment=''):
    """Bugalter -> admin zanjiri bo'yicha tasdiqlash."""
    if contract.status == Contract.Status.PENDING_BUGALTER:
        _require_role(user, bugalter=True)
        step = ContractApproval.Step.BUGALTER
        contract.status = Contract.Status.PENDING_ADMIN
    elif contract.status == Contract.Status.PENDING_ADMIN:
        _require_role(user, admin=True)
        step = ContractApproval.Step.ADMIN
        contract.status = Contract.Status.APPROVED
    else:
        raise ValidationError('Shartnoma tasdiqlash bosqichida emas.')

    contract.save()
    ContractApproval.objects.create(
        contract=contract,
        step=step,
        decision=ContractApproval.Decision.APPROVED,
        comment=comment,
        decided_by=user,
    )
    if contract.status == Contract.Status.APPROVED:
        Notification.objects.create(
            title=f'{contract.number}: admin tasdiqladi',
            message=(
                f"Oldindan to'lov {contract.prepayment_percent}% — "
                f'{contract.prepayment_amount} {contract.currency}. Pul kutilmoqda.'
            ),
            level=Notification.Level.INFO,
            entity='Contract',
            object_id=str(contract.pk),
        )
    return contract


@atomic
def reject_contract(contract, user, comment=''):
    """Bugalter yoki admin shartnomani rad etadi."""
    if contract.status == Contract.Status.PENDING_BUGALTER:
        _require_role(user, bugalter=True)
        step = ContractApproval.Step.BUGALTER
    elif contract.status == Contract.Status.PENDING_ADMIN:
        _require_role(user, admin=True)
        step = ContractApproval.Step.ADMIN
    else:
        raise ValidationError('Shartnoma tasdiqlash bosqichida emas.')

    contract.status = Contract.Status.REJECTED
    contract.save()
    ContractApproval.objects.create(
        contract=contract,
        step=step,
        decision=ContractApproval.Decision.REJECTED,
        comment=comment,
        decided_by=user,
    )
    return contract


@atomic
def confirm_payment(contract, user, *, amount, method=ContractPayment.Method.TRANSFER,
                    paid_at=None, is_prepayment=None):
    """Bugalter pul kelganini tasdiqlaydi — shu kundan muddat sanog'i boshlanadi."""
    _require_role(user, bugalter=True)
    if contract.status not in {Contract.Status.APPROVED, Contract.Status.ACTIVE}:
        raise ValidationError('Avval shartnoma admin tomonidan tasdiqlanishi kerak.')

    paid_at = paid_at or now()
    first_payment = contract.status == Contract.Status.APPROVED
    if is_prepayment is None:
        is_prepayment = first_payment

    payment = ContractPayment.objects.create(
        contract=contract,
        amount=amount,
        method=method,
        paid_at=paid_at,
        is_prepayment=is_prepayment,
        created_by=user,
        approved_by=user,
    )
    record_transaction(
        code='sale',
        amount=amount,
        occurred_at=paid_at,
        description=f'{contract.number} bo\'yicha to\'lov',
        currency=contract.currency,
        contract=contract,
        user=user,
        approved_by=user,
    )

    if first_payment:
        contract.start_date = paid_at.date()
        contract.status = Contract.Status.ACTIVE
    if contract.balance <= 0:
        contract.status = Contract.Status.COMPLETED
    contract.save()
    return payment
