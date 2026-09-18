from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from rest_framework.test import APITestCase

from apps.finance.models import Loan
from apps.finance.services import cash_balance
from apps.inventory.models import Product
from apps.procurement.models import Replenishment
from apps.purchases.models import Purchase, PurchaseDocument
from apps.sales.models import Contract, Lead


class SeedDemoTests(APITestCase):
    """seed_demo — butun tizim uchun bog'langan demo to'plami."""

    @classmethod
    def setUpTestData(cls):
        call_command('seed_demo', stdout=StringIO())

    def test_counts_per_module(self):
        # 5 asosiy mahsulot + engineer configuratordan qo'shgan Wi-Fi modul
        self.assertEqual(Product.objects.filter(base_model__isnull=True).count(), 6)
        # YANGI OQIM B1: D-hikoya tasdig'i ham avtomatik shartnoma ochadi
        self.assertEqual(Contract.objects.count(), 7)
        self.assertEqual(Lead.objects.count(), 5)
        # 5 ta qo'lda + 1 ta TLD receive'da avtomatik ochilgan KIR (§4.3)
        self.assertEqual(Purchase.objects.count(), 6)
        self.assertEqual(Replenishment.objects.count(), 4)
        self.assertEqual(PurchaseDocument.objects.count(), 2)

    def test_configurator_created_replenishment(self):
        """Engineer 'omborda yo'q' deb yuborgani: TLD konfiguratsiyaga bog'langan.

        Yangi oqim: hisob narxlanib SUBMIT qilingan — sales (zayavka egasi)
        mijoz roziligini olishi kutilmoqda; owner_sales to'ldirilgan.
        """
        from apps.accounts.models import User
        from apps.core.models import Notification

        linked = Replenishment.objects.get(configuration__isnull=False)
        self.assertEqual(linked.status, Replenishment.Status.PENDING_SALES)
        self.assertEqual(linked.owner_sales.username, 'sales1')
        skus = set(linked.items.values_list('product__sku', flat=True))
        self.assertIn('WIFI-6E', skus)

        # Buyurtmachi va bugalterga "omborda yo'q" xabari; egasi sales1 ga
        # "mijoz roziligi kerak" — boshqa sales (sales2) esa hech narsa olmaydi
        for username in ('buyurtmachi', 'bugalter', 'sales1'):
            user = User.objects.get(username=username)
            self.assertTrue(
                Notification.objects.filter(
                    user=user, entity='Replenishment',
                    object_id=str(linked.pk),
                ).exists(),
                f'{username} uchun xabar topilmadi',
            )
        sales2 = User.objects.get(username='sales2')
        self.assertFalse(
            Notification.objects.filter(
                user=sales2, entity='Replenishment', object_id=str(linked.pk),
            ).exists()
        )

    def test_engineer_added_product_from_configurator(self):
        """Bazada yo'q tovar configuratordan qo'shilgan (new_component_name uslubi)."""
        wifi = Product.objects.get(sku='WIFI-6E')
        self.assertEqual(wifi.kind, Product.Kind.COMPONENT)
        self.assertEqual(wifi.cost_price, Decimal('350000'))

    def test_active_contract_has_additional_payment(self):
        """Faol shartnomada 2 ta to'lov: 30% oldindan + qo'shimcha 5 mln."""
        # YANGI OQIM: D-hikoya to'lovi ham active — A-hikoyaniki birinchisi
        contract = (
            Contract.objects.filter(status=Contract.Status.ACTIVE)
            .order_by('id').first()
        )
        self.assertEqual(contract.payments.count(), 2)
        self.assertEqual(
            contract.paid, contract.prepayment_amount + Decimal('5000000'),
        )
        self.assertEqual(
            contract.payments.filter(is_prepayment=False).count(), 1,
        )

    def test_contract_statuses_cover_the_chain(self):
        """Har bosqichdan bittadan — endi yetkazilgan/yopilgan ham bor (#2)."""
        statuses = set(Contract.objects.values_list('status', flat=True))
        self.assertEqual(statuses, {
            Contract.Status.DRAFT, Contract.Status.PENDING_BUGALTER,
            Contract.Status.PENDING_ADMIN, Contract.Status.APPROVED,
            Contract.Status.ACTIVE, Contract.Status.COMPLETED,
        })

    def test_threshold_demo_contract_skipped_admin(self):
        """§11.3 demo: kichik shartnoma bugalter tasdig'i bilan approved,
        tarixda decided_by bo'sh avtomatik admin yozuvi bor."""
        from apps.sales.models import ContractApproval

        auto = ContractApproval.objects.filter(
            step=ContractApproval.Step.ADMIN, decided_by__isnull=True,
        )
        self.assertTrue(auto.exists())
        self.assertIn('chegara', auto.first().comment)

    def test_active_contract_awaits_shipment(self):
        """#2 demo: faol shartnoma yetkazilmagan — buyurtmachi navbatida."""
        active = (
            Contract.objects.filter(status=Contract.Status.ACTIVE)
            .order_by('id').first()
        )
        self.assertIsNone(active.delivered_at)
        completed = Contract.objects.get(status=Contract.Status.COMPLETED)
        self.assertIsNotNone(completed.delivered_at)

    def test_configuration_chain_states_present(self):
        """#4 demo: chernovik, sales ko'rigi, tasdiqlangan va sotilgan."""
        from apps.configurator.models import Configuration

        statuses = set(Configuration.objects.values_list('status', flat=True))
        self.assertEqual(statuses, {
            Configuration.Status.DRAFT, Configuration.Status.PENDING_SALES,
            Configuration.Status.APPROVED, Configuration.Status.SOLD,
        })
        # Partiya: A-hikoya konfiguratsiyasi 2 talik
        sold = Configuration.objects.get(status=Configuration.Status.SOLD)
        self.assertEqual(sold.quantity, 2)
        self.assertIsNotNone(sold.assembled_at)

    def test_reservations_exist(self):
        """§11.4 demo: qattiq (shartnoma) va yumshoq (chernovik) bronlar bor."""
        from apps.inventory.models import StockReservation

        kinds = set(
            StockReservation.objects.filter(
                status=StockReservation.Status.ACTIVE,
            ).values_list('kind', flat=True)
        )
        self.assertEqual(
            kinds, {StockReservation.Kind.HARD, StockReservation.Kind.SOFT},
        )

    def test_stale_contract_for_sla_demo(self):
        """SLA demo: Didox navbatidagi shartnoma 6 kun turib qolgan —
        admin my-work'da stale qator ko'radi."""
        from apps.accounts.models import User

        admin = User.objects.get(username='admin')
        self.client.force_authenticate(admin)
        work = self.client.get('/api/my-work/').data
        stale = [r for r in work['items'] if r.get('reason') == 'stale']
        self.assertTrue(stale)
        self.assertEqual(stale[0]['holder_role'], 'bugalter')

    def test_active_contract_is_in_red_zone(self):
        # YANGI OQIM: D-hikoya to'lovi ham active — A-hikoyaniki birinchisi
        contract = (
            Contract.objects.filter(status=Contract.Status.ACTIVE)
            .order_by('id').first()
        )
        self.assertEqual(contract.color, 'red')
        self.assertGreater(contract.paid, 0)

    def test_purchase_types_covered(self):
        types = set(Purchase.objects.values_list('type', flat=True))
        self.assertEqual(types, {
            Purchase.Type.LOCAL, Purchase.Type.IMPORT, Purchase.Type.USTAV,
        })
        self.assertTrue(Purchase.objects.filter(status=Purchase.Status.RECEIVED).exists())

    def test_supplier_debt_created_through_real_flow(self):
        """To'ldirish hisobi haqiqiy servislar orqali o'tgan: qarz 5 mln."""
        flow = Replenishment.objects.get(status=Replenishment.Status.DELIVERED)
        self.assertIsNotNone(flow.debt)
        self.assertEqual(flow.debt.amount, Decimal('5000000'))
        self.assertEqual(flow.debt.source, Loan.Source.SUPPLIER)
        self.assertGreaterEqual(flow.events.count(), 3)

    def test_low_stock_examples_exist(self):
        low = [p.sku for p in Product.objects.all() if p.is_low_stock and not p.is_variant]
        self.assertIn('GPU-32', low)
        self.assertIn('RAM-16', low)

    def test_cash_balance_is_positive_and_consistent(self):
        self.assertGreater(cash_balance(), 0)

    def test_second_run_does_not_duplicate(self):
        call_command('seed_demo', stdout=StringIO())
        # YANGI OQIM B1: D-hikoya tasdig'i ham avtomatik shartnoma ochadi
        self.assertEqual(Contract.objects.count(), 7)
        self.assertEqual(Purchase.objects.count(), 6)

    def test_dashboard_is_rich_after_seed(self):
        from apps.accounts.models import User

        self.client.force_authenticate(User.objects.get(username='admin'))
        response = self.client.get('/api/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.data['kassa']['income_total'], 0)
        self.assertTrue(response.data['deadlines'])
        self.assertTrue(response.data['ombor']['low_stock'])


class SeedDemoResetTests(APITestCase):
    """--reset: eski ma'lumotlar o'chadi, userlar qoladi, toza demo yuklanadi."""

    def test_reset_wipes_junk_and_reseeds(self):
        from django.core.management import call_command
        from io import StringIO

        from apps.accounts.models import User

        call_command('seed_demo', stdout=StringIO())
        # Foydalanuvchi "axlat" qo'shdi deb faraz qilamiz
        junk_user = User.objects.create_user('mening_akkauntim', password='p')
        Loan.objects.create(
            lender_name='test', amount=100,
            taken_at='2026-01-01', deadline='2026-02-01',
        )
        junk = Product.objects.create(sku='JUNK-1', name='Keraksiz mahsulot')

        call_command('seed_demo', '--reset', stdout=StringIO())

        # Axlat o'chdi, demo qayta yuklandi, akkauntlar joyida
        self.assertFalse(Product.objects.filter(sku='JUNK-1').exists())
        self.assertFalse(Loan.objects.filter(lender_name='test').exists())
        self.assertEqual(Loan.objects.count(), 2)
        # YANGI OQIM B1: D-hikoya tasdig'i ham avtomatik shartnoma ochadi
        self.assertEqual(Contract.objects.count(), 7)
        self.assertTrue(User.objects.filter(username='mening_akkauntim').exists())
        self.assertTrue(User.objects.filter(username='engineer').exists())

    def test_single_warehouse_only(self):
        """Biznesda bitta ombor — demo ikkinchi ombor yaratmaydi."""
        from django.core.management import call_command
        from io import StringIO

        from apps.inventory.models import Warehouse

        call_command('seed_demo', stdout=StringIO())
        self.assertEqual(Warehouse.objects.count(), 1)
        self.assertEqual(Warehouse.objects.get().name, 'Asosiy ombor')

    def test_engineer_included_in_demo(self):
        from django.core.management import call_command
        from io import StringIO

        from apps.accounts.models import User
        from apps.configurator.models import ConfigurationRequest

        call_command('seed_demo', stdout=StringIO())
        engineer = User.objects.get(username='engineer')
        self.assertEqual(engineer.role, User.Role.ENGINEER)
        self.assertTrue(engineer.check_password('Ombor2026!'))
        # Zayavkalar: yangi (hovuz), sales ko'rigida va bajarilganlar (#4)
        self.assertEqual(ConfigurationRequest.objects.count(), 4)
        done = ConfigurationRequest.objects.filter(
            status=ConfigurationRequest.Status.DONE,
        )
        self.assertTrue(done.exists())
        self.assertEqual(done.first().taken_by, engineer)
        self.assertIsNotNone(done.first().configuration)
        self.assertTrue(
            ConfigurationRequest.objects.filter(
                status=ConfigurationRequest.Status.NEW,
            ).exists()
        )
