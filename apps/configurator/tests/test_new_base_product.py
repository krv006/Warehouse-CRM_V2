from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.configurator.models import Configuration, ConfigurationRequest
from apps.inventory.models import Product, Warehouse


class NewBaseProductFromRequestTests(APITestCase):
    """21-§2: katalogda yo'q modelni zayavkadan to'g'ridan so'rash."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')

    def test_new_base_product_name_creates_machine(self):
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/configuration-requests/', {
            'text': 'Yangi Dell Precision 3680', 'client': self.mijoz.id,
            'quantity': 1, 'new_base_product_name': 'Dell Precision 3680',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        request_obj = ConfigurationRequest.objects.get(pk=response.data['id'])
        self.assertIsNotNone(request_obj.base_product)
        product = request_obj.base_product
        self.assertEqual(product.name, 'Dell Precision 3680')
        self.assertEqual(product.kind, Product.Kind.MACHINE)
        self.assertEqual(product.cost_price, Decimal('0'))
        self.assertEqual(product.sale_price, Decimal('0'))
        self.assertEqual(product.reorder_level, 0)
        self.assertTrue(product.sku.startswith('MAH-'))

    def test_same_name_twice_reuses_product(self):
        self.client.force_authenticate(self.sales)
        first = self.client.post('/api/configuration-requests/', {
            'text': 'birinchi', 'client': self.mijoz.id, 'quantity': 1,
            'new_base_product_name': 'Dell Precision 3680',
        }, format='json')
        second = self.client.post('/api/configuration-requests/', {
            'text': 'ikkinchi', 'client': self.mijoz.id, 'quantity': 1,
            'new_base_product_name': 'Dell Precision 3680',
        }, format='json')
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(second.status_code, 201, second.data)
        self.assertEqual(first.data['base_product'], second.data['base_product'])
        self.assertEqual(Product.objects.filter(name='Dell Precision 3680').count(), 1)

    def test_explicit_sku_used(self):
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/configuration-requests/', {
            'text': 'Dell', 'client': self.mijoz.id, 'quantity': 1,
            'new_base_product_name': 'Dell Precision 3680',
            'new_base_product_sku': 'DELL-3680',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        request_obj = ConfigurationRequest.objects.get(pk=response.data['id'])
        self.assertEqual(request_obj.base_product.sku, 'DELL-3680')

    def test_description_stored_on_product(self):
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/configuration-requests/', {
            'text': 'Dell', 'client': self.mijoz.id, 'quantity': 1,
            'new_base_product_name': 'Dell Precision 3680',
            'new_base_product_description': 'i7, 32GB RAM, RTX 4070',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        request_obj = ConfigurationRequest.objects.get(pk=response.data['id'])
        self.assertEqual(request_obj.base_product.description, 'i7, 32GB RAM, RTX 4070')

    def test_explicit_base_product_wins_over_new_name(self):
        existing = Product.objects.create(
            sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE,
        )
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/configuration-requests/', {
            'text': 'HP', 'client': self.mijoz.id, 'quantity': 1,
            'base_product': existing.id,
            'new_base_product_name': 'Boshqa nom',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['base_product'], existing.id)
        self.assertFalse(Product.objects.filter(name='Boshqa nom').exists())

    def test_line_new_base_product_works_the_same(self):
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/configuration-requests/', {
            'text': 'HP + yangi Dell', 'client': self.mijoz.id, 'quantity': 1,
            'new_base_product_name': 'HP 880',
            'lines': [
                {
                    'kind': 'model', 'quantity': 1, 'text': 'Dell',
                    'new_base_product_name': 'Dell Precision 3680',
                },
            ],
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        request_obj = ConfigurationRequest.objects.get(pk=response.data['id'])
        line = request_obj.lines.get()
        self.assertEqual(line.base_product.name, 'Dell Precision 3680')
        self.assertEqual(line.base_product.kind, Product.Kind.MACHINE)

    def test_patch_ignores_new_base_product_name(self):
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/configuration-requests/', {
            'text': 'boshlang\'ich', 'client': self.mijoz.id, 'quantity': 1,
        }, format='json')
        request_obj = ConfigurationRequest.objects.get(pk=response.data['id'])
        response = self.client.patch(f'/api/configuration-requests/{request_obj.id}/', {
            'new_base_product_name': 'Kutilmagan mahsulot',
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(Product.objects.filter(name='Kutilmagan mahsulot').exists())

    def test_sales_cannot_post_products_directly(self):
        """Regressiya: §2 yangi ruxsat qo'shmadi — `/products/` hamon yopiq."""
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/products/', {
            'sku': 'NEW-1', 'name': 'Yangi mahsulot',
        }, format='json')
        self.assertEqual(response.status_code, 403)

    def test_take_with_new_base_product_name(self):
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/configuration-requests/', {
            'text': 'Engineer o\'zi tanlaydi', 'client': self.mijoz.id, 'quantity': 1,
        }, format='json')
        request_obj = ConfigurationRequest.objects.get(pk=response.data['id'])

        self.client.force_authenticate(self.engineer)
        response = self.client.post(
            f'/api/configuration-requests/{request_obj.id}/take/',
            {'new_base_product_name': 'Dell Precision 3680', 'mode': 'build'},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        request_obj.refresh_from_db()
        self.assertIsNotNone(request_obj.configuration)
        self.assertEqual(request_obj.configuration.base_product.name, 'Dell Precision 3680')
        self.assertEqual(request_obj.configuration.base_product.kind, Product.Kind.MACHINE)

    def test_take_new_base_product_modify_mode_blocked_early(self):
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/configuration-requests/', {
            'text': 'yangi model', 'client': self.mijoz.id, 'quantity': 1,
        }, format='json')
        request_obj = ConfigurationRequest.objects.get(pk=response.data['id'])

        self.client.force_authenticate(self.engineer)
        response = self.client.post(
            f'/api/configuration-requests/{request_obj.id}/take/',
            {'new_base_product_name': 'Dell Precision 3680', 'mode': 'modify'},
            format='json',
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("omborda ham yo'q", str(response.data))
        self.assertEqual(Configuration.objects.count(), 0)

    def test_new_base_product_as_resale_line_needs_price_and_procurement(self):
        """§2.5(b): yangi modelni qayta sotish — model o'zi qator sifatida."""
        from apps.configurator.models import ConfigurationItem
        from apps.configurator.services import _missing_rows

        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/configuration-requests/', {
            'text': 'Tayyor Dell sotib olamiz', 'client': self.mijoz.id, 'quantity': 1,
            'new_base_product_name': 'Dell Precision 3680',
        }, format='json')
        request_obj = ConfigurationRequest.objects.get(pk=response.data['id'])

        self.client.force_authenticate(self.engineer)
        response = self.client.post(
            f'/api/configuration-requests/{request_obj.id}/take/',
            {'mode': 'build'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        request_obj.refresh_from_db()
        configuration = request_obj.configuration
        new_model = configuration.base_product

        ConfigurationItem.objects.create(
            configuration=configuration, component=new_model,
            label=new_model.name, quantity=1,
        )
        missing = _missing_rows(configuration)
        self.assertTrue(any(row['product'] == new_model.id for row in missing))
