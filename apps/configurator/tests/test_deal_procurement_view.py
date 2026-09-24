from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.configurator.models import Configuration, ConfigurationRequest
from apps.inventory.models import Product, ProductSpec, Warehouse
from apps.sales.models import Contract


class DealProcurementViewTests(APITestCase):
    """18-to'plam: TLD savdoda bitta, lekin ekranda ikkita bo'lib ko'rinardi —
    `deal.models[]` ga `missing`, `procurement`/`sent_to_procurement` esa
    zanjir (savdo) bo'yicha qidiriladi.
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
            sku='HP-880', name='HP EliteDesk 880 G9', kind=Product.Kind.MACHINE,
            sale_price=Decimal('12000000'),
        )
        self.dell = Product.objects.create(
            sku='DELL-7010', name='Dell OptiPlex 7010', kind=Product.Kind.MACHINE,
            sale_price=Decimal('10000000'),
        )
        # Ikkalasi ham HECH QACHON kirim qilinmagan butlovchiga muhtoj —
        # ikkalasi ham doim "yetishmaydi" tomonda, bir xil fizik zaxira
        # uchun raqobatlashmaydi (bron matematikasi murakkablashmasin)
        self.hp_part = Product.objects.create(
            sku='HP-NVME', name='Samsung 980 NVMe M.2 512 GB', kind=Product.Kind.COMPONENT,
            sale_price=Decimal('900000'),
        )
        self.dell_part = Product.objects.create(
            sku='DELL-NVME', name='Samsung 990 PRO', kind=Product.Kind.COMPONENT,
            sale_price=Decimal('950000'),
        )
        ProductSpec.objects.create(product=self.hp, component=self.hp_part, label='NVMe', quantity=1)
        ProductSpec.objects.create(product=self.dell, component=self.dell_part, label='NVMe', quantity=1)

    def _dual_model_request(self):
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/configuration-requests/', {
            'text': '10 ta HP 880 + 2 ta Dell',
            'base_product': self.hp.id, 'client': self.mijoz.id, 'quantity': 10,
            'lines': [
                {'kind': 'model', 'base_product': self.dell.id, 'quantity': 2, 'text': 'Dell'},
            ],
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return ConfigurationRequest.objects.get(pk=response.data['id'])

    def _single_model_request(self):
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/configuration-requests/', {
            'text': '10 ta HP 880', 'base_product': self.hp.id,
            'client': self.mijoz.id, 'quantity': 10,
        }, format='json')
        return ConfigurationRequest.objects.get(pk=response.data['id'])

    def _take(self, request_obj):
        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configuration-requests/{request_obj.id}/take/')
        self.assertEqual(response.status_code, 200, response.data)
        request_obj.refresh_from_db()
        return request_obj

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

    def _approved_dual_deal(self):
        request_obj = self._take(self._dual_model_request())
        primary = request_obj.configuration
        dell_config = request_obj.lines.get(base_product=self.dell).configuration

        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configuration-requests/{request_obj.id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)
        self.client.force_authenticate(self.sales)
        response = self.client.post(f'/api/configuration-requests/{request_obj.id}/approve/')
        self.assertEqual(response.status_code, 200, response.data)
        contract = Contract.objects.get()
        self._pay(contract)
        return request_obj, primary, dell_config, contract

    # -------------------------------------------------------------------- §1

    def test_deal_models_include_missing_list(self):
        """§1: ikki modelli savdo → `deal.models[*].missing` to'la (bo'sh emas)."""
        request_obj, primary, dell_config, _contract = self._approved_dual_deal()

        response = self.client.get(f'/api/configurations/{primary.id}/')
        self.assertEqual(response.status_code, 200, response.data)
        deal = response.data['deal']
        self.assertIsNotNone(deal)
        rows = {row['number']: row for row in deal['models']}
        self.assertEqual(set(rows), {primary.number, dell_config.number})

        hp_row = rows[primary.number]
        self.assertEqual(hp_row['missing_count'], 1)
        self.assertEqual(len(hp_row['missing']), 1)
        self.assertEqual(hp_row['missing'][0]['name'], self.hp_part.name)
        self.assertEqual(hp_row['missing'][0]['shortage'], 10)

        dell_row = rows[dell_config.number]
        self.assertEqual(dell_row['missing_count'], 1)
        self.assertEqual(dell_row['missing'][0]['name'], self.dell_part.name)
        self.assertEqual(dell_row['missing'][0]['shortage'], 2)

        # Ikkinchi model sahifasidan ham xuddi shu ro'yxat ko'rinadi
        response2 = self.client.get(f'/api/configurations/{dell_config.id}/')
        rows2 = {row['number']: row for row in response2.data['deal']['models']}
        self.assertEqual(rows2[primary.number]['missing'], hp_row['missing'])

    def test_single_model_deal_still_none_and_missing_unaffected(self):
        """§1/§2 regressiya: bitta modelli ZVKda `deal` null, `missing` o'zgarmaydi."""
        request_obj = self._take(self._single_model_request())
        configuration = request_obj.configuration

        response = self.client.get(f'/api/configurations/{configuration.id}/')
        self.assertIsNone(response.data['deal'])
        self.assertEqual(response.data['missing_count'], 1)
        self.assertEqual(response.data['missing'][0]['name'], self.hp_part.name)

    # -------------------------------------------------------------------- §2

    def test_sibling_model_sees_procurement_after_other_model_sends(self):
        """§2: model A dan TLD ochilsa — model B javobida ham `procurement`
        to'la va `sent_to_procurement` rost bo'lishi kerak."""
        request_obj, primary, dell_config, _contract = self._approved_dual_deal()

        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configurations/{primary.id}/request-procurement/')
        self.assertEqual(response.status_code, 201, response.data)
        replenishment_number = response.data['number']

        # Dell hech qachon o'zi request-procurement bosmagan — lekin
        # savdodagi TLD bitta bo'lgani uchun uning ham javobi to'la bo'lsin
        response2 = self.client.get(f'/api/configurations/{dell_config.id}/')
        self.assertTrue(response2.data['sent_to_procurement'])
        self.assertIsNotNone(response2.data['procurement'])
        self.assertEqual(response2.data['procurement']['number'], replenishment_number)
        self.assertEqual(response2.data['procurement']['opened_for'], primary.number)

        # Ikkinchi marta bosilsa ham — takror hisob ochilmaydi, o'shasi qaytadi
        response3 = self.client.post(f'/api/configurations/{dell_config.id}/request-procurement/')
        self.assertEqual(response3.status_code, 201, response3.data)
        self.assertEqual(response3.data['number'], replenishment_number)

    def test_single_model_chain_procurement_unaffected(self):
        """§2 regressiya: bitta modelli zanjirda `procurement` bugungidek ishlaydi."""
        request_obj = self._take(self._single_model_request())
        configuration = request_obj.configuration
        self.client.force_authenticate(self.engineer)
        self.client.post(f'/api/configurations/{configuration.id}/submit/')
        self.client.force_authenticate(self.sales)
        self.client.post(f'/api/configurations/{configuration.id}/approve/')
        contract = Contract.objects.get()
        self._pay(contract)

        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configurations/{configuration.id}/request-procurement/')
        self.assertEqual(response.status_code, 201, response.data)

        response2 = self.client.get(f'/api/configurations/{configuration.id}/')
        self.assertTrue(response2.data['sent_to_procurement'])
        self.assertEqual(response2.data['procurement']['number'], response.data['number'])
        self.assertEqual(response2.data['procurement']['opened_for'], configuration.number)
