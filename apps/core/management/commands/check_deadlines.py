from django.core.management.base import BaseCommand

from apps.core.models import Notification
from apps.core.utils import RED, RED_ZONE_DAYS, YELLOW
from apps.finance.models import Loan
from apps.purchases.models import Purchase
from apps.sales.models import Contract

LEVEL_BY_COLOR = {
    RED: Notification.Level.DANGER,
    YELLOW: Notification.Level.WARNING,
}


class Command(BaseCommand):
    """Shartnoma, qarz va import muddatlarini tekshirib eslatma yaratadi."""

    help = "Muddati yaqinlashgan shartnoma, qarz va importlar uchun eslatma yaratadi"

    def handle(self, *args, **options):
        created = 0
        created += self._check_contracts()
        created += self._check_loans()
        created += self._check_imports()
        self.stdout.write(self.style.SUCCESS(f'{created} ta eslatma yaratildi'))

    def _notify(self, *, title, message, color, entity, object_id, due_date):
        level = LEVEL_BY_COLOR.get(color)
        if not level:
            return 0
        exists = Notification.objects.filter(
            entity=entity, object_id=str(object_id), due_date=due_date, is_read=False,
        ).exists()
        if exists:
            return 0
        Notification.objects.create(
            title=title,
            message=message,
            level=level,
            entity=entity,
            object_id=str(object_id),
            due_date=due_date,
        )
        return 1

    def _check_contracts(self):
        created = 0
        contracts = Contract.objects.filter(status=Contract.Status.ACTIVE)
        for contract in contracts:
            progress = contract.progress
            created += self._notify(
                title=f'{contract.number}: {progress["days_left"]} kun qoldi',
                message=f'Qoldiq: {contract.balance} {contract.currency}',
                color=progress['color'],
                entity='Contract',
                object_id=contract.pk,
                due_date=progress['deadline'],
            )
        return created

    def _check_loans(self):
        created = 0
        for loan in Loan.objects.filter(status=Loan.Status.ACTIVE):
            if loan.days_left > RED_ZONE_DAYS:
                continue
            created += self._notify(
                title=f'Qarz muddati: {loan.lender_name}',
                message=f'{loan.balance} {loan.currency}, {loan.days_left} kun qoldi',
                color=loan.color,
                entity='Loan',
                object_id=loan.pk,
                due_date=loan.deadline,
            )
        return created

    def _check_imports(self):
        created = 0
        purchases = Purchase.objects.filter(
            status__in=[Purchase.Status.ORDERED, Purchase.Status.IN_TRANSIT],
        )
        for purchase in purchases:
            progress = purchase.progress
            created += self._notify(
                title=f'{purchase.number}: import muddati',
                message=f'{purchase.supplier} — {progress["days_left"]} kun qoldi',
                color=progress['color'],
                entity='Purchase',
                object_id=purchase.pk,
                due_date=progress['deadline'],
            )
        return created
