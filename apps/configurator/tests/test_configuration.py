from datetime import date
from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.configurator.models import Act, Configuration, ConfigurationItem
from apps.inventory.models import Product, StockMovement, Warehouse
from apps.inventory.services import apply_movement


class ConfigurationTests(APITestCase):
    """Configurator: omborda bori olinadi, yetishmagani kirim qilinadi."""

    def setUp(self):
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.admin = User.objects.create_user('admin', password='p', role=User.Role.ADMIN)
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.base = Product.objects.create(
            sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE,
        )
        self.ssd = Product.objects.create(
            sku='SSD-1TB', name='SSD 1 TB', kind=Product.Kind.COMPONENT,
        )
        self.gpu = Product.objects.create(
            sku='GPU-32', name='GPU 32', kind=Product.Kind.COMPONENT,
        )
        apply_movement(
            product=self.ssd, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('5'),
        )
        self.configuration = Configuration.objects.create(
            base_product=self.base, warehouse=self.warehouse, created_by=self.engineer,
        )
        ConfigurationItem.objects.create(
            configuration=self.configuration, component=self.ssd,
            label='SSD', quantity=1, unit_price=Decimal('1500000'),
        )
        ConfigurationItem.objects.create(
            configuration=self.configuration, component=self.gpu,
            label='GPU', quantity=1, unit_price=Decimal('4500000'),
        )
        self.client.force_authenticate(self.engineer)

    def test_number_is_generated(self):
        self.assertTrue(self.configuration.number.startswith('CFG-'))

    def test_stock_check_marks_missing_component(self):
        response = self.client.get(f'/api/configurations/{self.configuration.id}/stock-check/')
        self.assertEqual(response.status_code, 200)
        sources = {row['component']: row['source'] for row in response.data['items']}
        self.assertEqual(sources['SSD 1 TB'], 'stock')
        self.assertEqual(sources['GPU 32'], 'purchase')

    def test_total_price(self):
        self.assertEqual(self.configuration.total_price, Decimal('6000000'))

    def test_finalize_walks_new_chain(self):
        """#4: yakunlash bosqichma-bosqich — tasdiq, yig'ish, ACT, keyin ready.

        Har bir to'siq o'z xabari bilan 400 beradi, zanjir to'liq o'tgach 200.
        """
        self.client.force_authenticate(self.engineer)
        url = f'/api/configurations/{self.configuration.id}'

        # 1) Tasdiqlanmagan yechim yakunlanmaydi
        response = self.client.post(f'{url}/finalize/')
        self.assertEqual(response.status_code, 400)
        self.assertIn('texnik yechim', response.data['detail'])

        # 2) submit -> sales/admin approve
        self.assertEqual(self.client.post(f'{url}/submit/').status_code, 200)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(f'{url}/approve/').status_code, 200)
        self.client.force_authenticate(self.engineer)

        # 3) Yig'ilmagan — yakunlanmaydi
        response = self.client.post(f'{url}/finalize/')
        self.assertEqual(response.status_code, 400)
        self.assertIn("yig'ilsin", response.data['detail'])

        # GPU omborda yo'q edi — mol keldi deb hisoblaymiz
        apply_movement(
            product=self.gpu, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('10'),
        )
        self.assertEqual(self.client.post(f'{url}/assemble/').status_code, 200)

        # 4) ACT'siz yakunlanmaydi
        response = self.client.post(f'{url}/finalize/')
        self.assertEqual(response.status_code, 400)
        self.assertIn('ACT', response.data['detail'])

        act = Act.objects.create(
            number='ACT-001', title='Tarkib o\'zgarishi',
            issued_at=date.today(), created_by=self.admin,
        )
        response = self.client.post(f'{url}/finalize/', {'act': act.id}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], Configuration.Status.READY)

    def test_export_excel(self):
        response = self.client.get(f'/api/configurations/{self.configuration.id}/export-excel/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('spreadsheetml', response['Content-Type'])
        self.assertIn(self.configuration.number, response['Content-Disposition'])

    def test_act_belongs_to_engineer_stage(self):
        """§11.1: ACT ni engineer (va admin) kiritadi — sales emas."""
        payload = {'number': 'ACT-003', 'title': 'Yangi', 'issued_at': str(date.today())}
        self.client.force_authenticate(self.sales)
        self.assertEqual(self.client.post('/api/acts/', payload).status_code, 403)

        self.client.force_authenticate(self.engineer)
        self.assertEqual(self.client.post('/api/acts/', payload).status_code, 201)

        self.client.force_authenticate(self.admin)
        payload['number'] = 'ACT-004'
        self.assertEqual(self.client.post('/api/acts/', payload).status_code, 201)
