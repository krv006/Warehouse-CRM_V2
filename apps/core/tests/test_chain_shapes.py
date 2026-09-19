from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.configurator.models import Configuration, ConfigurationRequest
from apps.inventory.models import Product, Warehouse
from apps.sales.models import Contract, ContractItem


class ChainShapeRoadmapTests(APITestCase):
    """8-to'plam §1: zanjirda umuman bo'lmaydigan hujjat qadamlari skipped."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.admin = User.objects.create_user('adm', password='p', role=User.Role.ADMIN)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.product = Product.objects.create(
            sku='HP-880', name='HP 880', sale_price=Decimal('5000000'),
        )

    def test_manual_contract_chain_skips_zvk_and_cfg_steps(self):
        """Qo'lda ochilgan SHT: ZVK/CFG qadamlari skipped, joriy — completed."""
        from django.utils.timezone import localdate

        contract = Contract.objects.create(
            client=self.mijoz, total_amount=Decimal('5000000'),
            created_by=self.sales, status=Contract.Status.ACTIVE,
            delivered_at=localdate(),
        )
        ContractItem.objects.create(
            contract=contract, product=self.product, quantity=1,
            unit_price=Decimal('5000000'),
        )
        self.client.force_authenticate(self.admin)
        response = self.client.get(f'/api/contracts/{contract.id}/roadmap/')
        self.assertEqual(response.status_code, 200, response.data)
        steps = {s['key']: s for s in response.data['steps']}

        for key in ('zvk_created', 'taken', 'price_request', 'submitted',
                    'sales_review', 'procurement_sent', 'procurement_chain',
                    'assemble', 'finalize'):
            self.assertEqual(steps[key]['state'], 'skipped', key)
        self.assertEqual(steps['ship']['state'], 'done')
        # Yetkazilgan, balans ochiq — joriy qadam yakunlash (§2 kuzatuvi)
        self.assertEqual(response.data['current_key'], 'completed')

    def test_config_without_zvk_skips_request_steps_only(self):
        """ZVK'siz konfiguratsiya: zayavka qadami skipped, CFG qadamlari tirik."""
        configuration = Configuration.objects.create(
            base_product=self.product, warehouse=self.warehouse,
            created_by=self.engineer, client=self.mijoz,
        )
        self.client.force_authenticate(self.admin)
        response = self.client.get(
            f'/api/configurations/{configuration.id}/roadmap/',
        )
        steps = {s['key']: s for s in response.data['steps']}
        self.assertEqual(steps['zvk_created']['state'], 'skipped')
        self.assertEqual(steps['taken']['state'], 'done')
        self.assertEqual(response.data['current_key'], 'submitted')


class SingleContractPerConfigurationTests(APITestCase):
    """8-to'plam §3: bitta konfiguratsiyaga bitta shartnoma — qo'lda ham."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.base = Product.objects.create(
            sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE,
            sale_price=Decimal('5000000'),
        )
        self.configuration = Configuration.objects.create(
            base_product=self.base, created_by=self.sales, client=self.mijoz,
        )
        Contract.objects.create(
            client=self.mijoz, configuration=self.configuration,
            total_amount=Decimal('5000000'), created_by=self.sales,
        )

    def test_second_manual_contract_rejected(self):
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/contracts/', {
            'client': self.mijoz.id, 'configuration': self.configuration.id,
            'items': [{'product': self.base.id, 'quantity': 1,
                       'unit_price': '5000000'}],
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('configuration', response.data)
        self.assertEqual(Contract.objects.count(), 1)

    def test_allowed_after_cancellation(self):
        """Bekor qilingan shartnoma hisobga olinmaydi — zanjir o'lik."""
        Contract.objects.update(status=Contract.Status.CANCELLED)
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/contracts/', {
            'client': self.mijoz.id, 'configuration': self.configuration.id,
            'items': [{'product': self.base.id, 'quantity': 1,
                       'unit_price': '5000000'}],
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)


class CancelReasonTests(APITestCase):
    """8-to'plam §4: "nega to'xtadi?" javobi konfiguratsiyaning o'zida."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.base = Product.objects.create(
            sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE,
        )

    def _taken_request(self):
        self.client.force_authenticate(self.sales)
        request_id = self.client.post('/api/configuration-requests/', {
            'text': 'HP 880', 'base_product': self.base.id,
            'client': self.mijoz.id,
        }, format='json').data['id']
        self.client.force_authenticate(self.engineer)
        take = self.client.post(f'/api/configuration-requests/{request_id}/take/')
        return request_id, Configuration.objects.get(pk=take.data['configuration'])

    def test_release_stores_reason_on_configuration(self):
        """9-§2 yo'li: bog'lanish uzilsa ham sabab hujjatda qoladi (javobda ham)."""
        request_id, configuration = self._taken_request()
        response = self.client.post(
            f'/api/configuration-requests/{request_id}/release/',
            {'comment': 'Vaqtim yo\'q'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        configuration.refresh_from_db()
        self.assertEqual(configuration.status, Configuration.Status.CANCELLED)
        self.assertEqual(configuration.cancel_reason, 'Vaqtim yo\'q')
        # Engineer o'z hujjatida sababni ko'radi
        response = self.client.get(f'/api/configurations/{configuration.id}/')
        self.assertEqual(response.data['cancel_reason'], 'Vaqtim yo\'q')

    def test_cancel_chain_stores_reason(self):
        request_id, configuration = self._taken_request()
        self.client.force_authenticate(self.sales)
        self.client.post(
            f'/api/configuration-requests/{request_id}/cancel/',
            {'reason': 'Mijoz voz kechdi'}, format='json',
        )
        configuration.refresh_from_db()
        self.assertEqual(configuration.cancel_reason, 'Mijoz voz kechdi')
