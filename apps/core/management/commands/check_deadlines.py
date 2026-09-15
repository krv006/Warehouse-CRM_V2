from django.core.management.base import BaseCommand
from django.utils.timezone import localdate

from apps.core.models import Notification
from apps.core.utils import RED, RED_ZONE_DAYS, YELLOW
from apps.finance.models import Loan
from apps.purchases.models import Purchase
from apps.sales.models import Contract, Lead

LEAD_REMIND_DAYS = 1

LEVEL_BY_COLOR = {
    RED: Notification.Level.DANGER,
    YELLOW: Notification.Level.WARNING,
}


class Command(BaseCommand):
    """Shartnoma, qarz, import va kelishuv muddatlarini tekshirib eslatma yaratadi."""

    help = (
        "Muddati yaqinlashgan shartnoma, qarz, import va kelishuv aloqalari "
        "uchun eslatma yaratadi"
    )

    def handle(self, *args, **options):
        created = 0
        created += self._check_contracts()
        created += self._check_loans()
        created += self._check_imports()
        created += self._check_leads()
        created += self._expire_reservations()
        self.stdout.write(self.style.SUCCESS(f'{created} ta eslatma yaratildi'))

    def _expire_reservations(self):
        """§11.4: muddati o'tgan bronlar bo'shaydi, hujjat egasiga xabar boradi.

        Chernovik omborni abadiy band qilib turmasin: muddat CompanyProfile'da
        (admin belgilaydi), 0 bo'lsa bron muddatsiz.
        """
        from apps.inventory.models import StockReservation

        created = 0
        expired = StockReservation.objects.filter(
            status=StockReservation.Status.ACTIVE,
            expires_at__isnull=False,
            expires_at__lt=localdate(),
        ).select_related('contract__created_by', 'configuration__created_by', 'product')
        for reservation in expired:
            owner = reservation.contract or reservation.configuration
            reservation.status = StockReservation.Status.EXPIRED
            reservation.release_note = 'Muddati o\'tdi — avtomatik bo\'shatildi'
            reservation.save()
            recipient = owner.created_by if owner else None
            if recipient:
                Notification.objects.create(
                    user=recipient,
                    title=f'{owner.number} broni muddati tugadi',
                    message=(
                        f'{reservation.product.name} x{reservation.quantity} yana erkin. '
                        'Hujjatni yuborsangiz/yangilasangiz qayta bron qilinadi.'
                    ),
                    level=Notification.Level.WARNING,
                    entity='StockReservation',
                    object_id=str(reservation.pk),
                )
                created += 1
        return created

    def _notify(self, *, title, message, color, entity, object_id, due_date, user=None):
        level = LEVEL_BY_COLOR.get(color)
        if not level:
            return 0
        exists = Notification.objects.filter(
            entity=entity, object_id=str(object_id), due_date=due_date, is_read=False,
        ).exists()
        if exists:
            return 0
        Notification.objects.create(
            user=user,
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

    def _check_leads(self):
        """Kelishuvda "Keyingi aloqa" sanasi yaqin yoki o'tgan bo'lsa salesga eslatadi.

        Sana kiritilmagan kelishuvga eslatma yozilmaydi; yopilganlariga
        (shartnoma tuzildi / yo'qotildi) ham tegilmaydi.
        """
        created = 0
        today = localdate()
        leads = Lead.objects.select_related('client', 'created_by').filter(
            next_contact_at__isnull=False,
        ).exclude(stage__in=[Lead.Stage.CONTRACT, Lead.Stage.LOST])
        for lead in leads:
            contact_date = localdate(lead.next_contact_at)
            days_left = (contact_date - today).days
            if days_left > LEAD_REMIND_DAYS:
                continue
            if days_left < 0:
                color = RED
                message = (
                    f"Aloqa {abs(days_left)} kun oldin bo'lishi kerak edi — "
                    f'mijoz: {lead.client}'
                )
            else:
                color = YELLOW
                when = 'Bugun' if days_left == 0 else 'Ertaga'
                message = f'{when} mijoz bilan aloqa qilish kerak: {lead.client}'
            created += self._notify(
                title=f'Kelishuv: {lead.title}',
                message=message,
                color=color,
                entity='Lead',
                object_id=lead.pk,
                due_date=contact_date,
                user=lead.created_by,
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
