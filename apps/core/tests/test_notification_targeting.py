from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.utils.timezone import localdate

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.core.models import Notification
from apps.finance.models import Loan
from apps.inventory.models import Product, Warehouse
from apps.purchases.models import Purchase
from apps.sales.models import Contract


class DeadlineTargetingTests(APITestCase):
    """§4 (SIDEBAR-VA-EGALIK): check_deadlines endi user=None yozmaydi.

    Shartnoma — egasi + bugalter + admin; qarz — bugalter + admin;
    kirim — bugalter + buyurtmachi. Engineer hech narsa olmaydi.
    """

    def setUp(self):
        self.admin = User.objects.create_user('adm', password='p', role=User.Role.ADMIN)
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.buyurtmachi = User.objects.create_user(
            'buy', password='p', role=User.Role.SUPPLIER,
        )
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )

    def _run(self):
        call_command('check_deadlines', stdout=StringIO())

    def test_contract_deadline_goes_to_owner_and_finance(self):
        Contract.objects.create(
            client=self.mijoz, total_amount=Decimal('100000000'),
            status=Contract.Status.ACTIVE, term_days=90,
            start_date=localdate() - timedelta(days=85),
            created_by=self.sales,
        )
        self._run()

        notes = Notification.objects.filter(entity='Contract')
        recipients = set(notes.values_list('user__username', flat=True))
        self.assertEqual(recipients, {'adm', 'bug', 'sal'})
        self.assertFalse(notes.filter(user__isnull=True).exists())
        # Engineer shartnoma summasini ko'rmaydi
        self.assertFalse(notes.filter(user=self.engineer).exists())

    def test_loan_deadline_finance_only(self):
        Loan.objects.create(
            lender_name='Bobur aka', amount=Decimal('5000000'),
            taken_at=localdate() - timedelta(days=25),
            deadline=localdate() + timedelta(days=5),
        )
        self._run()
        recipients = set(
            Notification.objects.filter(entity='Loan')
            .values_list('user__username', flat=True)
        )
        self.assertEqual(recipients, {'adm', 'bug'})

    def test_import_deadline_bugalter_and_supplier(self):
        warehouse = Warehouse.objects.create(name='Asosiy ombor')
        Purchase.objects.create(
            supplier='Etuf', warehouse=warehouse, type=Purchase.Type.IMPORT,
            status=Purchase.Status.IN_TRANSIT,
            lead_days=30, ordered_at=localdate() - timedelta(days=25),
        )
        self._run()
        recipients = set(
            Notification.objects.filter(entity='Purchase')
            .values_list('user__username', flat=True)
        )
        self.assertEqual(recipients, {'bug', 'buy'})

    def test_idempotent_per_user(self):
        Contract.objects.create(
            client=self.mijoz, total_amount=Decimal('100000000'),
            status=Contract.Status.ACTIVE, term_days=90,
            start_date=localdate() - timedelta(days=85),
            created_by=self.sales,
        )
        self._run()
        self._run()
        self.assertEqual(Notification.objects.filter(entity='Contract').count(), 3)


class OwnerSalesTargetingTests(APITestCase):
    """§4.2: sales hovuz emas — zayavka egasigina xabar oladi."""

    def setUp(self):
        from apps.configurator.models import Configuration, ConfigurationRequest
        from apps.inventory.services import main_warehouse

        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.owner = User.objects.create_user('sales1', password='p', role=User.Role.SALES)
        self.other = User.objects.create_user('sales2', password='p', role=User.Role.SALES)
        self.buyurtmachi = User.objects.create_user(
            'buy', password='p', role=User.Role.SUPPLIER,
        )
        self.warehouse = main_warehouse()
        base = Product.objects.create(sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE)
        self.configuration = Configuration.objects.create(
            base_product=base, warehouse=self.warehouse, created_by=self.engineer,
            # #4: ta'minot faqat sales tasdiqlagan yechim uchun
            status=Configuration.Status.APPROVED,
        )
        ConfigurationRequest.objects.create(
            text='HP 880 kerak', created_by=self.owner,
            configuration=self.configuration,
        )
        from apps.configurator.models import ConfigurationItem

        gpu = Product.objects.create(
            sku='GPU-1', name='GPU', kind=Product.Kind.COMPONENT,
            cost_price=Decimal('4000000'),
        )
        ConfigurationItem.objects.create(
            configuration=self.configuration, component=gpu, label='GPU', quantity=1,
        )
        # YANGI OQIM B4: ta'minot faqat to'langan (active) shartnoma bilan
        from apps.clients.models import Client
        from apps.sales.models import Contract

        mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        Contract.objects.create(
            client=mijoz, configuration=self.configuration,
            status=Contract.Status.ACTIVE, total_amount=Decimal('1000000'),
            created_by=self.owner,
        )

    def test_request_procurement_notifies_owner_not_pool(self):
        self.client.force_authenticate(self.engineer)
        response = self.client.post(
            f'/api/configurations/{self.configuration.id}/request-procurement/',
        )
        self.assertEqual(response.status_code, 201, response.data)

        from apps.procurement.models import Replenishment

        replenishment = Replenishment.objects.get()
        # Egasi hisobga yozib qo'yildi (§4.3)
        self.assertEqual(replenishment.owner_sales, self.owner)
        # Xabar: egasi oladi, boshqa sales olmaydi
        self.assertTrue(Notification.objects.filter(user=self.owner).exists())
        self.assertFalse(Notification.objects.filter(user=self.other).exists())

    def test_client_approval_notifies_owner_only(self):
        self.client.force_authenticate(self.engineer)
        self.client.post(
            f'/api/configurations/{self.configuration.id}/request-procurement/',
        )
        Notification.objects.all().delete()

        from apps.procurement.models import Replenishment

        replenishment = Replenishment.objects.get()
        self.client.force_authenticate(self.buyurtmachi)
        response = self.client.post(f'/api/replenishments/{replenishment.id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)

        notes = Notification.objects.filter(title__contains='mijoz roziligi')
        self.assertEqual(notes.count(), 1)
        self.assertEqual(notes.get().user, self.owner)
