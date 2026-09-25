from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.configurator.models import Configuration, ConfigurationRequest
from apps.inventory.models import Product, StockMovement, Warehouse
from apps.inventory.services import apply_movement
from apps.sales.models import Contract, ContractDocument


class EngineerQueueReasonTests(APITestCase):
    """21-§4: to'langan+tasdiqlangan CFG'da butlovchi yetmasa navbat
    sababi "Yig'ish" emas, "Buyurtmachiga yuborish" bo'lishi kerak."""

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

    def _pay(self, contract):
        from apps.sales.services import approve_contract, confirm_didox, confirm_payment, send_didox

        self.client.force_authenticate(self.sales)
        ContractDocument.objects.update_or_create(contract=contract, defaults={'body': '<p>x</p>'})
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

    def _paid_configuration_missing_component(self):
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/configuration-requests/', {
            'text': '1 ta HP 880', 'base_product': self.hp.id,
            'client': self.mijoz.id, 'quantity': 1,
        }, format='json')
        request_obj = ConfigurationRequest.objects.get(pk=response.data['id'])
        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configuration-requests/{request_obj.id}/take/')
        self.assertEqual(response.status_code, 200, response.data)
        request_obj.refresh_from_db()
        configuration = request_obj.configuration

        from apps.configurator.models import ConfigurationItem

        ConfigurationItem.objects.create(
            configuration=configuration, component=self.part,
            label='NVMe', quantity=1, unit_price=Decimal('900000'),
        )

        response = self.client.post(f'/api/configurations/{configuration.id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)
        self.client.force_authenticate(self.sales)
        response = self.client.post(f'/api/configurations/{configuration.id}/approve/')
        self.assertEqual(response.status_code, 200, response.data)
        contract = Contract.objects.get()
        self._pay(contract)
        return configuration

    def _engineer_reason(self, configuration):
        self.client.force_authenticate(self.engineer)
        work = self.client.get('/api/my-work/').data
        rows = [
            row for row in work['items']
            if row['section'] == 'configurations' and row['id'] == configuration.id
        ]
        self.assertEqual(len(rows), 1, work['items'])
        return rows[0]['reason'], rows[0]['level']

    def test_missing_components_shows_request_procurement(self):
        configuration = self._paid_configuration_missing_component()
        self.assertTrue(configuration.missing_items)
        reason, level = self._engineer_reason(configuration)
        self.assertEqual(reason, 'request_procurement')
        self.assertEqual(level, 'warning')

    def test_open_tld_hides_request_procurement_reason(self):
        configuration = self._paid_configuration_missing_component()
        self.client.force_authenticate(self.engineer)
        response = self.client.post(
            f'/api/configurations/{configuration.id}/request-procurement/',
        )
        self.assertEqual(response.status_code, 201, response.data)

        reason, level = self._engineer_reason(configuration)
        self.assertNotEqual(reason, 'assemble')
        self.assertEqual(reason, 'procurement_pending')
        self.assertEqual(level, 'info')

    def test_sufficient_stock_still_shows_assemble(self):
        apply_movement(
            product=self.part, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('10'),
        )
        configuration = self._paid_configuration_missing_component()
        self.assertFalse(configuration.missing_items)
        reason, level = self._engineer_reason(configuration)
        self.assertEqual(reason, 'assemble')
        self.assertEqual(level, 'warning')
