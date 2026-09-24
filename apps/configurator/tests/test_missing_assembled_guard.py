from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.configurator.models import ConfigurationRequest
from apps.inventory.models import Product, ProductSpec, StockMovement, Warehouse
from apps.inventory.services import apply_movement
from apps.sales.models import Contract


class MissingExcludesAssembledTests(APITestCase):
    """19-§1: yig'ilgan model to'ldirish hisobiga (TLD) kirmasligi kerak —
    `missing_items` "hozir yig'sam nima yetmaydi" hisobi, yig'ilgandan
    keyin ham nolga tushmaydi (butlovchilar ombordan allaqachon chiqqan).
    """

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.admin = User.objects.create_user('adm', password='p', role=User.Role.ADMIN)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.hp = Product.objects.create(
            sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE,
            sale_price=Decimal('12000000'),
        )
        self.part = Product.objects.create(
            sku='NVME-1', name='Samsung NVMe', kind=Product.Kind.COMPONENT,
            sale_price=Decimal('900000'),
        )
        ProductSpec.objects.create(product=self.hp, component=self.part, label='NVMe', quantity=1)

    def _pay(self, contract):
        from apps.sales.services import approve_contract, confirm_didox, confirm_payment, send_didox

        self.client.force_authenticate(self.sales)
        response = self.client.post(f'/api/contracts/{contract.id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)
        contract.refresh_from_db()
        approve_contract(contract, self.admin)
        contract.refresh_from_db()
        if contract.status == Contract.Status.PENDING_ADMIN:
            approve_contract(contract, self.admin)
            contract.refresh_from_db()
        send_didox(contract, self.admin, 'DDX-1')
        confirm_didox(contract, self.admin)
        contract.refresh_from_db()
        confirm_payment(contract, self.admin, amount=contract.total_amount)
        contract.refresh_from_db()

    def _assembled_configuration(self):
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/configuration-requests/', {
            'text': '2 ta HP 880', 'base_product': self.hp.id,
            'client': self.mijoz.id, 'quantity': 2,
        }, format='json')
        request_obj = ConfigurationRequest.objects.get(pk=response.data['id'])

        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configuration-requests/{request_obj.id}/take/')
        self.assertEqual(response.status_code, 200, response.data)
        request_obj.refresh_from_db()
        configuration = request_obj.configuration

        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configurations/{configuration.id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)
        self.client.force_authenticate(self.sales)
        response = self.client.post(f'/api/configurations/{configuration.id}/approve/')
        self.assertEqual(response.status_code, 200, response.data)
        contract = Contract.objects.get()
        self._pay(contract)

        # Aynan kerakli miqdorda — yig'ilgach zaxira 0 ga tushadi, lekin
        # "kerak" (retsept) o'sha-o'sha qoladi, ya'ni `missing` yig'ilgandan
        # keyin ham NOLGA TUSHMAYDI (jonli holatdagi kabi)
        apply_movement(
            product=self.part, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('2'),
        )
        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configurations/{configuration.id}/assemble/')
        self.assertEqual(response.status_code, 200, response.data)
        configuration.refresh_from_db()
        self.assertTrue(configuration.assembled_at)
        return configuration

    def test_request_procurement_blocked_when_all_models_assembled(self):
        """19-§1: yig'ilgan model → `request-procurement` 400, yangi TLD ochilmaydi."""
        from apps.procurement.models import Replenishment

        configuration = self._assembled_configuration()
        # `missing_items` yig'ilgandan keyin ham nolga tushmasligini tekshiramiz
        self.assertTrue(configuration.missing_items)

        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configurations/{configuration.id}/request-procurement/')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("Yig'ilmagan model yo'q", str(response.data['detail']))
        self.assertFalse(Replenishment.objects.exists())

    def test_request_procurement_still_400_when_stock_sufficient(self):
        """Regressiya: yig'ilmagan-u ombor yetarli bo'lsa eski xabar qoladi."""
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/configuration-requests/', {
            'text': '1 ta HP 880', 'base_product': self.hp.id,
            'client': self.mijoz.id, 'quantity': 1,
        }, format='json')
        request_obj = ConfigurationRequest.objects.get(pk=response.data['id'])
        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configuration-requests/{request_obj.id}/take/')
        request_obj.refresh_from_db()
        configuration = request_obj.configuration

        apply_movement(
            product=self.part, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('10'),
        )
        response = self.client.post(f'/api/configurations/{configuration.id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)
        self.client.force_authenticate(self.sales)
        response = self.client.post(f'/api/configurations/{configuration.id}/approve/')
        self.assertEqual(response.status_code, 200, response.data)
        contract = Contract.objects.get()
        self._pay(contract)

        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configurations/{configuration.id}/request-procurement/')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('omborda yetarli', str(response.data['detail']))
