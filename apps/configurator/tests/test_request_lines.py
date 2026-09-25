from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.configurator.models import Configuration, ConfigurationRequest, ConfigurationRequestLine
from apps.inventory.models import Product, ProductSpec, StockMovement, Warehouse
from apps.inventory.services import apply_movement
from apps.sales.models import Contract


class RequestLinesTests(APITestCase):
    """12-§2 (B): bitta zayavkada bir nechta talab — model va tovar qatorlari."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.hp = Product.objects.create(
            sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE,
            sale_price=Decimal('12000000'),
        )
        self.dell = Product.objects.create(
            sku='DELL-7010', name='Dell OptiPlex 7010', kind=Product.Kind.MACHINE,
            sale_price=Decimal('10000000'),
        )
        self.ssd = Product.objects.create(
            sku='SSD-1TB', name='Zapas SSD 1TB', kind=Product.Kind.COMPONENT,
            sale_price=Decimal('900000'),
        )
        ProductSpec.objects.create(product=self.hp, component=self.ssd, label='SSD', quantity=1)
        ProductSpec.objects.create(product=self.dell, component=self.ssd, label='SSD', quantity=1)
        apply_movement(
            product=self.ssd, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('50'),
        )

    def _create_mixed_request(self):
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/configuration-requests/', {
            'text': '10 ta HP 880 + 20 ta Dell + 20 ta zapas SSD',
            'base_product': self.hp.id, 'client': self.mijoz.id, 'quantity': 10,
            'lines': [
                {'kind': 'model', 'base_product': self.dell.id, 'quantity': 20, 'text': 'Dell'},
                {'kind': 'item', 'base_product': self.ssd.id, 'quantity': 20, 'text': 'zapas'},
            ],
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return ConfigurationRequest.objects.get(pk=response.data['id'])

    def test_create_stores_extra_lines(self):
        request_obj = self._create_mixed_request()
        self.assertEqual(request_obj.lines.count(), 2)
        self.assertEqual(
            set(request_obj.lines.values_list('kind', flat=True)),
            {ConfigurationRequestLine.Kind.MODEL, ConfigurationRequestLine.Kind.ITEM},
        )

    def test_single_line_request_unaffected(self):
        """Regressiya: oddiy (bitta modelli) zayavka avvalgidek ishlaydi."""
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/configuration-requests/', {
            'text': '2 ta HP 880', 'base_product': self.hp.id,
            'client': self.mijoz.id, 'quantity': 2,
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        request_obj = ConfigurationRequest.objects.get(pk=response.data['id'])
        self.assertEqual(request_obj.lines.count(), 0)

        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configuration-requests/{request_obj.id}/take/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Configuration.objects.count(), 1)

    def test_take_opens_configuration_per_model_line(self):
        """B2: bitta amal — N chernovik (asosiy + qo'shimcha MODEL qatorlari)."""
        request_obj = self._create_mixed_request()
        self.client.force_authenticate(self.engineer)
        response = self.client.post(
            f'/api/configuration-requests/{request_obj.id}/take/',
            {'mode': 'build'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)

        # Ikkita konfiguratsiya: asosiy (HP) + qo'shimcha model qatori (Dell)
        self.assertEqual(Configuration.objects.count(), 2)
        request_obj.refresh_from_db()
        self.assertIsNotNone(request_obj.configuration)
        self.assertEqual(request_obj.configuration.base_product, self.hp)

        dell_line = request_obj.lines.get(kind=ConfigurationRequestLine.Kind.MODEL)
        self.assertIsNotNone(dell_line.configuration_id)
        self.assertEqual(dell_line.configuration.base_product, self.dell)
        self.assertEqual(dell_line.configuration.quantity, 20)

        # Tovar qatoriga konfiguratsiya ochilmaydi
        item_line = request_obj.lines.get(kind=ConfigurationRequestLine.Kind.ITEM)
        self.assertIsNone(item_line.configuration_id)

    def test_line_without_explicit_mode_inherits_shared_mode(self):
        """21-§6: `line_modes` berilmasa qator ham umumiy `mode`ni oladi,
        BUILD'ga to'g'ridan tushib qolmaydi."""
        request_obj = self._create_mixed_request()
        self.client.force_authenticate(self.engineer)
        response = self.client.post(
            f'/api/configuration-requests/{request_obj.id}/take/',
            {'mode': 'modify'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)

        dell_line = request_obj.lines.get(kind=ConfigurationRequestLine.Kind.MODEL)
        self.assertEqual(dell_line.configuration.mode, Configuration.Mode.MODIFY)
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.configuration.mode, Configuration.Mode.MODIFY)

    def test_model_line_rejects_non_machine_product(self):
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/configuration-requests/', {
            'text': 'xato qator', 'base_product': self.hp.id,
            'client': self.mijoz.id, 'quantity': 1,
            'lines': [{'kind': 'model', 'base_product': self.ssd.id, 'quantity': 1}],
        }, format='json')
        request_obj = ConfigurationRequest.objects.get(pk=response.data['id'])
        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configuration-requests/{request_obj.id}/take/')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(Configuration.objects.count(), 0)  # atomic — hech narsa ochilmadi

    def _take_and_approve_primary(self, request_obj):
        self.client.force_authenticate(self.engineer)
        self.client.post(f'/api/configuration-requests/{request_obj.id}/take/')
        request_obj.refresh_from_db()
        primary = request_obj.configuration
        self.client.post(f'/api/configurations/{primary.id}/submit/')
        self.client.force_authenticate(self.sales)
        response = self.client.post(f'/api/configurations/{primary.id}/approve/')
        self.assertEqual(response.status_code, 200, response.data)
        return primary

    def test_item_line_attaches_to_contract_when_it_opens(self):
        """B: TOVAR qatori konfiguratorsiz — shartnoma ochilishi bilan qatorga aylanadi."""
        request_obj = self._create_mixed_request()
        self._take_and_approve_primary(request_obj)

        contract = Contract.objects.get()
        item_line = request_obj.lines.get(kind=ConfigurationRequestLine.Kind.ITEM)
        item_line.refresh_from_db()
        self.assertIsNotNone(item_line.contract_item_id)
        self.assertEqual(item_line.contract_item.product, self.ssd)
        self.assertEqual(item_line.contract_item.quantity, 20)
        self.assertIn(item_line.contract_item, contract.items.all())
        self.assertEqual(contract.total_amount, contract.items_total_with_vat)

    def test_request_done_only_after_all_lines_complete(self):
        """B3: barcha qatorlar (model + tovar) tugagunicha DONE bo'lmaydi."""
        request_obj = self._create_mixed_request()
        primary = self._take_and_approve_primary(request_obj)
        contract = Contract.objects.get()

        # Faqat asosiy (HP) va tovar (SSD) tugadi — Dell hali draft
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, ConfigurationRequest.Status.IN_PROGRESS)

        dell_line = request_obj.lines.get(kind=ConfigurationRequestLine.Kind.MODEL)
        self.client.force_authenticate(self.engineer)
        self.client.post(f'/api/configurations/{dell_line.configuration.id}/submit/')
        self.client.force_authenticate(self.sales)
        response = self.client.post(
            f'/api/configurations/{dell_line.configuration.id}/approve/',
            {'contract': contract.id}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)

        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, ConfigurationRequest.Status.DONE)
        contract.refresh_from_db()
        self.assertEqual(contract.items.count(), 3)  # HP + Dell + SSD

    def test_release_cancels_all_line_configurations(self):
        """Ish hovuzga qaytsa — asosiy VA qo'shimcha model chernoviklari bekor bo'ladi."""
        request_obj = self._create_mixed_request()
        self.client.force_authenticate(self.engineer)
        self.client.post(f'/api/configuration-requests/{request_obj.id}/take/')
        request_obj.refresh_from_db()
        dell_line = request_obj.lines.get(kind=ConfigurationRequestLine.Kind.MODEL)
        dell_config_id = dell_line.configuration_id
        primary_config_id = request_obj.configuration_id

        response = self.client.post(
            f'/api/configuration-requests/{request_obj.id}/release/',
            {'comment': 'vaqtim yo\'q'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)

        self.assertEqual(
            Configuration.objects.get(pk=primary_config_id).status,
            Configuration.Status.CANCELLED,
        )
        self.assertEqual(
            Configuration.objects.get(pk=dell_config_id).status,
            Configuration.Status.CANCELLED,
        )
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, ConfigurationRequest.Status.NEW)
        self.assertIsNone(request_obj.configuration_id)
        dell_line.refresh_from_db()
        self.assertIsNone(dell_line.configuration_id)
