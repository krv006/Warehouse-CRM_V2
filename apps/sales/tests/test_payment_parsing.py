from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.inventory.models import Product, StockMovement, Warehouse
from apps.inventory.services import apply_movement
from apps.sales.models import Contract, ContractDocument


class ConfirmPaymentParsingTests(APITestCase):
    """confirm-payment: summa satr bo'lib kelsa ham 500 emas — 200 yoki 400."""

    def setUp(self):
        self.sales = User.objects.create_user('sales', password='p', role=User.Role.SALES)
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.admin = User.objects.create_user('admin', password='p', role=User.Role.ADMIN)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        warehouse = Warehouse.objects.create(name='Asosiy ombor')
        product = Product.objects.create(
            sku='ADS-1', name='adas', sale_price=Decimal('5000000'),
        )
        apply_movement(
            product=product, warehouse=warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('5'),
        )
        self.client.force_authenticate(self.sales)
        self.contract_id = self.client.post('/api/contracts/', {
            'client': self.mijoz.id,
            'items': [{'product': product.id, 'quantity': 1, 'unit_price': '5000000'}],
        }, format='json').data['id']
        # Zanjir: submit -> bugalter -> admin -> Didox (12-§1)
        ContractDocument.objects.update_or_create(
            contract=Contract.objects.get(pk=self.contract_id), defaults={'body': '<p>x</p>'},
        )
        self.client.post(f'/api/contracts/{self.contract_id}/submit/')
        self.client.force_authenticate(self.bugalter)
        self.client.post(f'/api/contracts/{self.contract_id}/approve/')
        self.client.force_authenticate(self.admin)
        self.client.post(f'/api/contracts/{self.contract_id}/approve/')
        self.client.force_authenticate(self.bugalter)
        self.client.post(
            f'/api/contracts/{self.contract_id}/send-didox/',
            {'didox_number': 'DDX-1'}, format='json',
        )
        self.client.post(f'/api/contracts/{self.contract_id}/confirm-didox/')

    def _confirm(self, body):
        return self.client.post(
            f'/api/contracts/{self.contract_id}/confirm-payment/', body, format='json',
        )

    def test_string_amount_is_accepted(self):
        response = self._confirm({'amount': '1680000'})
        self.assertEqual(response.status_code, 200, response.data)
        contract = Contract.objects.get(pk=self.contract_id)
        self.assertEqual(contract.paid, Decimal('1680000'))
        self.assertEqual(contract.status, Contract.Status.ACTIVE)

    def test_garbage_amount_is_400_not_500(self):
        response = self._confirm({'amount': 'abc'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('amount', response.data)
