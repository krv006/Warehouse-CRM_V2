from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.configurator.models import Configuration, ConfigurationItem
from apps.core.models import Notification
from apps.inventory.models import Product, ProductSpec, Warehouse


class FrontFixesTests(APITestCase):
    """Front topgan xatolar regressiyasi.

    1. POST /configuration-items/ — serializer'da `configuration` bor (500 emas).
    2. Zayavka yaratilganda engineerlarga Notification boradi.
    3. /configuration-requests/ da `configuration` filtri ishlaydi.
    4. ready/attached konfiguratsiya PATCH/DELETE'dan himoyalangan.
    5. take/ chernovik konfiguratsiyani zavod tarkibi bilan ochadi.
    """

    def setUp(self):
        self.sales = User.objects.create_user('sales', password='p', role=User.Role.SALES)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.base = Product.objects.create(
            sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE,
        )
        self.ssd = Product.objects.create(
            sku='SSD-1TB', name='SSD 1 TB', kind=Product.Kind.COMPONENT,
            sale_price=Decimal('1500000'),
        )
        ProductSpec.objects.create(
            product=self.base, component=self.ssd, label='SSD', quantity=1,
        )
        self.configuration = Configuration.objects.create(
            base_product=self.base, warehouse=self.warehouse, created_by=self.engineer,
        )
        self.client.force_authenticate(self.engineer)

    # ------------------------------------------------- 1: configuration-items
    def test_item_create_with_configuration(self):
        response = self.client.post('/api/configuration-items/', {
            'configuration': self.configuration.id,
            'component': self.ssd.id,
            'label': 'SSD qo\'shimcha',
            'quantity': 1,
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['configuration'], self.configuration.id)

    def test_item_create_without_configuration_is_400_not_500(self):
        response = self.client.post('/api/configuration-items/', {
            'component': self.ssd.id, 'label': 'SSD', 'quantity': 1,
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('configuration', response.data)

    # --------------------------------------------- 2: engineer notification
    def test_new_request_notifies_engineers(self):
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/configuration-requests/', {
            'text': 'HP 880, lekin SSD 2 TB bo\'lsin',
            'base_product': self.base.id,
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        note = Notification.objects.get(user=self.engineer)
        self.assertIn('yangi zayavka', note.title)
        self.assertEqual(note.entity, 'ConfigurationRequest')

    # ------------------------------------------------ 3: configuration filtri
    def test_requests_filter_by_configuration(self):
        self.client.force_authenticate(self.sales)
        for _ in range(2):
            self.client.post('/api/configuration-requests/', {
                'text': 'zayavka', 'base_product': self.base.id,
            }, format='json')

        self.client.force_authenticate(self.engineer)
        listing = self.client.get('/api/configuration-requests/').data['results']
        self.client.post(f"/api/configuration-requests/{listing[0]['id']}/take/")

        taken = self.client.get(f"/api/configuration-requests/{listing[0]['id']}/").data
        response = self.client.get(
            f"/api/configuration-requests/?configuration={taken['configuration']}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], listing[0]['id'])

    # --------------------------------------------------- 4: status qo'riqchisi
    def test_ready_configuration_is_locked(self):
        self.configuration.status = Configuration.Status.READY
        self.configuration.save()

        response = self.client.patch(
            f'/api/configurations/{self.configuration.id}/',
            {'note': 'o\'zgartirish'}, format='json',
        )
        self.assertEqual(response.status_code, 400)

        item = ConfigurationItem.objects.create(
            configuration=self.configuration, component=self.ssd,
            label='SSD', quantity=1,
        )
        response = self.client.patch(
            f'/api/configuration-items/{item.id}/', {'quantity': 2}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            self.client.delete(f'/api/configurations/{self.configuration.id}/').status_code,
            400,
        )

    def test_draft_configuration_is_editable(self):
        response = self.client.patch(
            f'/api/configurations/{self.configuration.id}/',
            {'note': 'chernovik tahriri'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)

    # ----------------------------------------------- 5: take auto-konfiguratsiya
    def test_take_opens_draft_with_factory_spec(self):
        self.client.force_authenticate(self.sales)
        request_id = self.client.post('/api/configuration-requests/', {
            'text': 'HP 880 standart', 'base_product': self.base.id,
            'warehouse': self.warehouse.id,
        }, format='json').data['id']

        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configuration-requests/{request_id}/take/')
        self.assertEqual(response.status_code, 200, response.data)

        configuration = Configuration.objects.get(pk=response.data['configuration'])
        self.assertEqual(configuration.warehouse, self.warehouse)
        labels = list(configuration.items.values_list('label', flat=True))
        self.assertEqual(labels, ['SSD'])

    def test_take_without_base_product_is_400(self):
        self.client.force_authenticate(self.sales)
        request_id = self.client.post('/api/configuration-requests/', {
            'text': 'model hali noma\'lum',
        }, format='json').data['id']

        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configuration-requests/{request_id}/take/')
        self.assertEqual(response.status_code, 400)
        self.assertIn('base_product', response.data)

    def test_take_body_overrides_request_base_product(self):
        other = Product.objects.create(
            sku='HP-990', name='HP 990', kind=Product.Kind.MACHINE,
        )
        self.client.force_authenticate(self.sales)
        request_id = self.client.post('/api/configuration-requests/', {
            'text': 'HP 880 deb yozilgan, lekin 990 kerak', 'base_product': self.base.id,
        }, format='json').data['id']

        self.client.force_authenticate(self.engineer)
        response = self.client.post(
            f'/api/configuration-requests/{request_id}/take/',
            {'base_product': other.id, 'mode': 'modify'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        configuration = Configuration.objects.get(pk=response.data['configuration'])
        self.assertEqual(configuration.base_product, other)
        self.assertEqual(configuration.mode, Configuration.Mode.MODIFY)

    def test_take_rejects_component_as_base(self):
        self.client.force_authenticate(self.sales)
        request_id = self.client.post('/api/configuration-requests/', {
            'text': 'x',
        }, format='json').data['id']

        self.client.force_authenticate(self.engineer)
        response = self.client.post(
            f'/api/configuration-requests/{request_id}/take/',
            {'base_product': self.ssd.id}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('base_product', response.data)
