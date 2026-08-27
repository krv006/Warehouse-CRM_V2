from datetime import date
from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.configurator.models import Act, Configuration, ConfigurationItem
from apps.inventory.models import Category, Product, StockMovement, Warehouse
from apps.inventory.services import apply_movement
from apps.purchases.models import Purchase


class ConfigurationTests(APITestCase):
    """Configurator: omborda bori olinadi, yetishmagani kirim qilinadi."""

    def setUp(self):
        self.sales = User.objects.create_user('sales', password='p', role=User.Role.SALES)
        self.admin = User.objects.create_user('admin', password='p', role=User.Role.ADMIN)
        self.category = Category.objects.create(name='Kompyuter')
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.base = Product.objects.create(
            sku='HP-880', name='HP 880', category=self.category, kind=Product.Kind.MACHINE,
        )
        self.ssd = Product.objects.create(
            sku='SSD-1TB', name='SSD 1 TB', category=self.category, kind=Product.Kind.COMPONENT,
        )
        self.gpu = Product.objects.create(
            sku='GPU-32', name='GPU 32', category=self.category, kind=Product.Kind.COMPONENT,
        )
        apply_movement(
            product=self.ssd, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('5'),
        )
        self.configuration = Configuration.objects.create(
            base_product=self.base, warehouse=self.warehouse, created_by=self.sales,
        )
        ConfigurationItem.objects.create(
            configuration=self.configuration, component=self.ssd,
            label='SSD', quantity=1, unit_price=Decimal('1500000'),
        )
        ConfigurationItem.objects.create(
            configuration=self.configuration, component=self.gpu,
            label='GPU', quantity=1, unit_price=Decimal('4500000'),
        )
        self.client.force_authenticate(self.sales)

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

    def test_finalize_requires_act(self):
        response = self.client.post(f'/api/configurations/{self.configuration.id}/finalize/')
        self.assertEqual(response.status_code, 400)

        act = Act.objects.create(
            number='ACT-001', title='Tarkib o\'zgarishi',
            issued_at=date.today(), created_by=self.admin,
        )
        self.configuration.act = act
        self.configuration.save()
        response = self.client.post(f'/api/configurations/{self.configuration.id}/finalize/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], Configuration.Status.READY)

    def test_attach_to_purchase(self):
        act = Act.objects.create(number='ACT-002', title='ACT', issued_at=date.today())
        self.configuration.act = act
        self.configuration.status = Configuration.Status.READY
        self.configuration.save()
        purchase = Purchase.objects.create(
            supplier='Etuf', warehouse=self.warehouse, type=Purchase.Type.LOCAL,
        )
        response = self.client.post(
            f'/api/configurations/{self.configuration.id}/attach/',
            {'purchase': purchase.id},
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], Configuration.Status.ATTACHED)

    def test_export_excel(self):
        response = self.client.get(f'/api/configurations/{self.configuration.id}/export-excel/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('spreadsheetml', response['Content-Type'])
        self.assertIn(self.configuration.number, response['Content-Disposition'])

    def test_act_is_admin_only(self):
        payload = {'number': 'ACT-003', 'title': 'Yangi', 'issued_at': str(date.today())}
        self.assertEqual(self.client.post('/api/acts/', payload).status_code, 403)

        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post('/api/acts/', payload).status_code, 201)
