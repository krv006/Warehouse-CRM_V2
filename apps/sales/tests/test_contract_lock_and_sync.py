from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.inventory.models import Product
from apps.sales.models import Contract


class ContractTotalSyncTests(APITestCase):
    """§10.3: qator o'zgarganda total_amount avtomatik yangilanadi."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.product = Product.objects.create(
            sku='ADS-1', name='adas', sale_price=Decimal('5000000'),
        )
        self.client.force_authenticate(self.sales)
        self.contract_id = self.client.post('/api/contracts/', {
            'client': self.mijoz.id,
            'items': [{'product': self.product.id, 'quantity': 1, 'unit_price': '5000000'}],
        }, format='json').data['id']

    def _total(self):
        return Contract.objects.get(pk=self.contract_id).total_amount

    def test_adding_item_resyncs_total(self):
        # Boshlang'ich: 5 000 000 + 12% = 5 600 000
        self.assertEqual(self._total(), Decimal('5600000.00'))
        response = self.client.post('/api/contract-items/', {
            'contract': self.contract_id, 'product': self.product.id,
            'quantity': 1, 'unit_price': '1000000',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        # 6 000 000 + 12% = 6 720 000
        self.assertEqual(self._total(), Decimal('6720000.00'))

    def test_updating_item_resyncs_total(self):
        item_id = Contract.objects.get(pk=self.contract_id).items.get().id
        self.client.patch(
            f'/api/contract-items/{item_id}/', {'quantity': 2}, format='json',
        )
        self.assertEqual(self._total(), Decimal('11200000.00'))

    def test_deleting_item_resyncs_total(self):
        item_id = Contract.objects.get(pk=self.contract_id).items.get().id
        self.client.delete(f'/api/contract-items/{item_id}/')
        self.assertEqual(self._total(), Decimal('0.00'))

    def test_item_without_contract_is_400(self):
        response = self.client.post('/api/contract-items/', {
            'product': self.product.id, 'quantity': 1, 'unit_price': '1',
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('contract', response.data)


class ContractLockTests(APITestCase):
    """§10.3/§11.3 asosi: tasdiqqa yuborilgan shartnoma qulflanadi.

    Aks holda kichik summa bilan tasdiq olib, keyin qatorlarni katta
    summaga o'zgartirish mumkin bo'lardi.
    """

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.admin = User.objects.create_user('adm', password='p', role=User.Role.ADMIN)
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Vali Aliyev',
            passport='AA2223334', jshshir='22223333444455', phone='+998900000002',
        )
        self.product = Product.objects.create(
            sku='ADS-2', name='adas 2', sale_price=Decimal('5000000'),
        )
        self.client.force_authenticate(self.sales)
        data = self.client.post('/api/contracts/', {
            'client': self.mijoz.id,
            'items': [{'product': self.product.id, 'quantity': 1, 'unit_price': '5000000'}],
        }, format='json').data
        self.contract_id = data['id']
        self.item_id = data['items'][0]['id']

    def test_items_locked_after_submit(self):
        self.client.post(f'/api/contracts/{self.contract_id}/submit/')
        response = self.client.patch(
            f'/api/contract-items/{self.item_id}/', {'unit_price': '50000000'},
            format='json',
        )
        self.assertEqual(response.status_code, 403)
        # Shartnomaning o'zi (nested items bilan) ham qulf
        response = self.client.patch(
            f'/api/contracts/{self.contract_id}/', {'note': 'x'}, format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_still_edits_after_submit(self):
        self.client.post(f'/api/contracts/{self.contract_id}/submit/')
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            f'/api/contract-items/{self.item_id}/', {'quantity': 2}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)

    def test_rejected_contract_is_editable_and_resubmittable(self):
        self.client.post(f'/api/contracts/{self.contract_id}/submit/')
        self.client.force_authenticate(self.bugalter)
        self.client.post(
            f'/api/contracts/{self.contract_id}/reject/', {'comment': 'Narx xato'},
        )
        self.client.force_authenticate(self.sales)
        response = self.client.patch(
            f'/api/contract-items/{self.item_id}/', {'unit_price': '4500000'},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        response = self.client.post(f'/api/contracts/{self.contract_id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], Contract.Status.PENDING_BUGALTER)
