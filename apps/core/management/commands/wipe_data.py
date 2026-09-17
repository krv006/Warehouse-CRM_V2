from django.core.management.base import BaseCommand
from django.db.transaction import atomic


class Command(BaseCommand):
    """Barcha biznes ma'lumotni o'chiradi — demo yuklamasdan.

    QOLADI: foydalanuvchi akkauntlari, bajaruvchi rekvizitlari
    (CompanyProfile — chegaralar/SLA sozlamalari bilan) va kassa
    yacheykalari (CashCategory — tizim ma'lumotnomasi).
    O'CHADI: qolgan hammasi — mijozlar, shartnomalar, konfiguratsiyalar,
    zayavkalar, TLD, kirimlar, kassa harakatlari, qarzlar, ombor
    (mahsulot/qoldiq/harakat/bron), eslatmalar, audit.

    Qaytarib bo'lmaydi — shuning uchun --yes bayrog'i majburiy.
    """

    help = "Bazani tozalaydi (userlar, rekvizitlar va yacheykalar qoladi; demo yuklamaydi)"

    def add_arguments(self, parser):
        parser.add_argument(
            '--yes',
            action='store_true',
            help="Tasdiq: ha, barcha biznes ma'lumot o'chirilsin",
        )

    @atomic
    def handle(self, *args, **options):
        if not options['yes']:
            self.stdout.write(self.style.ERROR(
                "Bu komanda BARCHA biznes ma'lumotni o'chiradi va uni "
                "qaytarib bo'lmaydi. Rozimisiz? Unda: wipe_data --yes "
                "(oldin zaxira: make backup)"
            ))
            return

        from apps.clients.models import Client
        from apps.configurator.models import (
            Act,
            Configuration,
            ConfigurationApproval,
            ConfigurationItem,
            ConfigurationRemoval,
            ConfigurationRequest,
        )
        from apps.core.models import ActivityLog, Notification
        from apps.finance.models import CashTransaction, ExpenseRequest, Loan
        from apps.inventory.models import (
            Product,
            ProductSpec,
            Stock,
            StockMovement,
            StockReservation,
            Warehouse,
        )
        from apps.procurement.models import (
            Replenishment,
            ReplenishmentApproval,
            ReplenishmentEvent,
            ReplenishmentItem,
        )
        from apps.purchases.models import Purchase, PurchaseDocument, PurchaseItem
        from apps.sales.models import (
            Contract,
            ContractApproval,
            ContractItem,
            ContractPayment,
            Lead,
        )

        # O'chirish tartibi PROTECT bog'lanishlarga mos: avval bolalar, keyin otalar
        ordered = [
            Notification, ActivityLog,
            StockReservation,
            CashTransaction, ExpenseRequest,
            ReplenishmentEvent, ReplenishmentApproval, ReplenishmentItem, Replenishment,
            Loan,
            PurchaseDocument, PurchaseItem,
            ContractPayment, ContractApproval, ContractItem,
            Lead,
            ConfigurationRequest, ConfigurationApproval, ConfigurationRemoval,
            ConfigurationItem, Configuration,
            Contract, Purchase,
            Act,
            StockMovement, Stock, ProductSpec, Product,
            Warehouse, Client,
        ]
        total = 0
        for model in ordered:
            deleted, _ = model.objects.all().delete()
            total += deleted
        self.stdout.write(self.style.SUCCESS(
            f"Baza tozalandi: {total} ta yozuv o'chirildi. "
            "Foydalanuvchilar, rekvizitlar va kassa yacheykalari joyida."
        ))
