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
        self.assertEqual(Product.objects.filter(base_model__isnull=True).count(), 5)
        self.assertEqual(Contract.objects.count(), 5)
        self.assertEqual(Lead.objects.count(), 5)
        self.assertEqual(Purchase.objects.count(), 5)
        self.assertEqual(Replenishment.objects.count(), 2)
        self.assertEqual(PurchaseDocument.objects.count(), 2)

    def test_contract_statuses_cover_the_chain(self):
        statuses = set(Contract.objects.values_list('status', flat=True))
        self.assertEqual(statuses, {
            Contract.Status.DRAFT, Contract.Status.PENDING_BUGALTER,
            Contract.Status.PENDING_ADMIN, Contract.Status.APPROVED,
            Contract.Status.ACTIVE,
        })

    def test_active_contract_is_in_red_zone(self):
        contract = Contract.objects.get(status=Contract.Status.ACTIVE)
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
        self.assertEqual(Contract.objects.count(), 5)
        self.assertEqual(Purchase.objects.count(), 5)

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
        self.assertEqual(Contract.objects.count(), 5)
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
        # Zayavkalar: yangi va engineer bajargan
        self.assertEqual(ConfigurationRequest.objects.count(), 2)
        done = ConfigurationRequest.objects.get(status=ConfigurationRequest.Status.DONE)
        self.assertEqual(done.taken_by, engineer)
        self.assertIsNotNone(done.configuration)
