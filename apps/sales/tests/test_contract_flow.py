from datetime import timedelta
from decimal import Decimal

from django.utils.timezone import localdate
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.core.utils import GREEN, RED, YELLOW
from apps.finance.models import CashTransaction
from apps.inventory.models import Product
from apps.sales.models import Contract, ContractApproval, ContractItem


class ContractFlowTests(APITestCase):
    """Sales -> bugalter -> admin -> to'lov zanjiri va muddat sanog'i."""

    def setUp(self):
        self.sales = User.objects.create_user('sales', password='p', role=User.Role.SALES)
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.admin = User.objects.create_user('admin', password='p', role=User.Role.ADMIN)
        self.client_obj = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.product = Product.objects.create(sku='HP-880', name='HP 880')

    def _contract(self, total='500000000'):
        contract = Contract.objects.create(
            client=self.client_obj, total_amount=Decimal(total), created_by=self.sales,
        )
        ContractItem.objects.create(
            contract=contract, product=self.product, quantity=1, unit_price=Decimal(total),
        )
        return contract

    def test_filter_by_configuration(self):
        """Front CFG bo'yicha qidirganda faqat o'sha shartnoma chiqadi (server bug'i)."""
        from apps.configurator.models import Configuration

        configuration = Configuration.objects.create(base_product=self.product)
        with_config = self._contract()
        with_config.configuration = configuration
        with_config.save()
        self._contract()  # konfiguratsiyasiz ikkinchi shartnoma

        self.client.force_authenticate(self.sales)
        response = self.client.get(f'/api/contracts/?configuration={configuration.id}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], with_config.id)

    def test_number_and_prepayment_percent_under_threshold(self):
        contract = self._contract('500000000')
        self.assertTrue(contract.number.startswith('SHT-'))
        self.assertEqual(contract.prepayment_percent, Decimal('30.00'))
        self.assertEqual(contract.prepayment_amount, Decimal('150000000.00'))

    def test_prepayment_percent_over_threshold(self):
        contract = self._contract('2000000000')
        self.assertEqual(contract.prepayment_percent, Decimal('15.00'))
        self.assertEqual(contract.prepayment_amount, Decimal('300000000.00'))

    def test_percent_can_be_overridden(self):
        contract = self._contract('500000000')
        contract.prepayment_percent = Decimal('50')
        contract.save()
        self.assertEqual(contract.prepayment_amount, Decimal('250000000.00'))

    def test_full_approval_chain(self):
        contract = self._contract()

        self.client.force_authenticate(self.sales)
        response = self.client.post(f'/api/contracts/{contract.id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], Contract.Status.PENDING_BUGALTER)

        # Admin bosqichiga yetmasdan admin tasdig'i o'tmaydi — avval bugalter
        self.client.force_authenticate(self.bugalter)
        response = self.client.post(f'/api/contracts/{contract.id}/approve/')
        self.assertEqual(response.data['status'], Contract.Status.PENDING_ADMIN)

        # Bugalter admin bosqichini tasdiqlay olmaydi
        response = self.client.post(f'/api/contracts/{contract.id}/approve/')
        self.assertEqual(response.status_code, 403)

        self.client.force_authenticate(self.admin)
        response = self.client.post(f'/api/contracts/{contract.id}/approve/')
        self.assertEqual(response.data['status'], Contract.Status.APPROVED)
        self.assertEqual(
            list(ContractApproval.objects.values_list('step', flat=True)),
            [ContractApproval.Step.BUGALTER, ContractApproval.Step.ADMIN],
        )

    def test_sales_cannot_approve(self):
        contract = self._contract()
        contract.status = Contract.Status.PENDING_BUGALTER
        contract.save()
        self.client.force_authenticate(self.sales)
        self.assertEqual(
            self.client.post(f'/api/contracts/{contract.id}/approve/').status_code, 403,
        )

    def test_payment_starts_countdown_and_hits_kassa(self):
        contract = self._contract()
        contract.status = Contract.Status.APPROVED
        contract.save()

        self.client.force_authenticate(self.bugalter)
        response = self.client.post(f'/api/contracts/{contract.id}/confirm-payment/')
        self.assertEqual(response.status_code, 200, response.data)

        contract.refresh_from_db()
        self.assertEqual(contract.status, Contract.Status.ACTIVE)
        self.assertEqual(contract.start_date, localdate())
        self.assertEqual(contract.paid, contract.prepayment_amount)

        transaction = CashTransaction.objects.get()
        self.assertEqual(transaction.category.code, 'sale')
        self.assertEqual(transaction.amount, contract.prepayment_amount)

    def test_timeline_colors(self):
        contract = self._contract()
        contract.status = Contract.Status.ACTIVE
        contract.term_days = 90
        contract.start_date = localdate()
        contract.save()

        self.client.force_authenticate(self.sales)
        response = self.client.get(f'/api/contracts/{contract.id}/timeline/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['days_left'], 90)
        self.assertEqual(response.data['color'], GREEN)
        self.assertEqual(len(response.data['points']), 91)

        contract.start_date = localdate() - timedelta(days=65)
        contract.save()
        self.assertEqual(contract.color, YELLOW)

        contract.start_date = localdate() - timedelta(days=85)
        contract.save()
        self.assertEqual(contract.days_left, 5)
        self.assertEqual(contract.color, RED)

    def test_prices_hidden_from_bugalter(self):
        contract = self._contract()
        self.client.force_authenticate(self.bugalter)
        response = self.client.get(f'/api/contracts/{contract.id}/')
        self.assertNotIn('unit_price', response.data['items'][0])

        self.client.force_authenticate(self.sales)
        response = self.client.get(f'/api/contracts/{contract.id}/')
        self.assertIn('unit_price', response.data['items'][0])


class ContractShipmentTests(APITestCase):
    """TZ 3.1, 9: sotuv tasdiqlanganda mahsulot ombordan chiqim qilinadi."""

    def setUp(self):
        from apps.inventory.models import StockMovement, Warehouse
        from apps.inventory.services import apply_movement

        self.sales = User.objects.create_user('sales', password='p', role=User.Role.SALES)
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.client_obj = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112224', jshshir='11112222333345', phone='+998900000002',
        )
        self.product = Product.objects.create(
            sku='HP-880', name='HP 880', sale_price=Decimal('25000000'),
        )
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        apply_movement(
            product=self.product, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('3'),
        )

    def _approved_contract(self, quantity):
        contract = Contract.objects.create(
            client=self.client_obj, status=Contract.Status.APPROVED,
            total_amount=self.product.sale_price * quantity,
            created_by=self.sales,
        )
        ContractItem.objects.create(
            contract=contract, product=self.product, quantity=quantity,
            unit_price=self.product.sale_price,
        )
        return contract

    def test_first_payment_ships_goods_from_stock(self):
        from apps.inventory.models import StockMovement
        from apps.inventory.services import available_quantity

        contract = self._approved_contract(2)
        self.client.force_authenticate(self.bugalter)
        response = self.client.post(f'/api/contracts/{contract.id}/confirm-payment/')
        self.assertEqual(response.status_code, 200, response.data)

        # Qoldiq 3 -> 1, harakat sabab 'sale' bilan yozilgan
        self.assertEqual(available_quantity(self.product, self.warehouse), Decimal('1'))
        movement = StockMovement.objects.get(reason=StockMovement.Reason.SALE)
        self.assertEqual(movement.reference, contract.number)

        # Ikkinchi to'lov qayta chiqim qilmaydi
        self.client.post(f'/api/contracts/{contract.id}/confirm-payment/', {'amount': '1000'})
        self.assertEqual(available_quantity(self.product, self.warehouse), Decimal('1'))

    def test_payment_blocked_when_stock_insufficient(self):
        from apps.finance.models import CashTransaction
        from apps.inventory.services import available_quantity

        contract = self._approved_contract(5)  # omborda faqat 3 ta
        self.client.force_authenticate(self.bugalter)
        response = self.client.post(f'/api/contracts/{contract.id}/confirm-payment/')
        self.assertEqual(response.status_code, 400)
        self.assertIn('HP 880', str(response.data['items']))

        # Hech narsa yozilmagan: qoldiq joyida, to'lov ham, kassa ham yo'q
        self.assertEqual(available_quantity(self.product, self.warehouse), Decimal('3'))
        self.assertFalse(CashTransaction.objects.exists())
        contract.refresh_from_db()
        self.assertEqual(contract.status, Contract.Status.APPROVED)
