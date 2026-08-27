from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.configurator.models import Configuration, ConfigurationRequest
from apps.core.models import Notification
from apps.inventory.models import Product


class ConfigurationRequestFlowTests(APITestCase):
    """Sales matnli zayavka yuboradi, Engineer konfiguratsiya qilib qaytaradi."""

    def setUp(self):
        self.sales = User.objects.create_user('sales', password='p', role=User.Role.SALES)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.base = Product.objects.create(
            sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE,
        )

    def _request(self, **extra):
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/configuration-requests/', {
            'text': 'Client kuchli kompyuter xohlaydi: SSD 2 TB, GPU zo\'r bo\'lsin.',
            'base_product': self.base.id,
            **extra,
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data['id']

    def test_sales_creates_request_with_number(self):
        request_id = self._request()
        request_obj = ConfigurationRequest.objects.get(pk=request_id)
        self.assertTrue(request_obj.number.startswith('ZVK-'))
        self.assertEqual(request_obj.created_by, self.sales)
        self.assertEqual(request_obj.status, ConfigurationRequest.Status.NEW)

    def test_engineer_takes_and_completes(self):
        request_id = self._request()

        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configuration-requests/{request_id}/take/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], ConfigurationRequest.Status.IN_PROGRESS)
        self.assertEqual(response.data['taken_by'], self.engineer.id)

        # take chernovik konfiguratsiyani avtomatik ochadi
        configuration_id = response.data['configuration']
        self.assertIsNotNone(configuration_id)
        configuration = Configuration.objects.get(pk=configuration_id)
        self.assertEqual(configuration.base_product, self.base)
        self.assertEqual(configuration.status, Configuration.Status.DRAFT)

        response = self.client.post(
            f'/api/configuration-requests/{request_id}/complete/',
            {'configuration': configuration.id}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], ConfigurationRequest.Status.DONE)
        self.assertEqual(response.data['configuration'], configuration.id)

        # Sales'ga xabar boradi — u eski jarayonni (shartnoma) boshlaydi
        note = Notification.objects.get(entity='ConfigurationRequest', user=self.sales)
        self.assertIn('tayyor', note.title)

    def test_sales_cannot_take_or_complete(self):
        request_id = self._request()
        self.client.force_authenticate(self.sales)
        self.assertEqual(
            self.client.post(f'/api/configuration-requests/{request_id}/take/').status_code, 403,
        )
        self.assertEqual(
            self.client.post(
                f'/api/configuration-requests/{request_id}/complete/', {}, format='json',
            ).status_code, 403,
        )

    def test_bugalter_reads_but_cannot_write(self):
        request_id = self._request()
        self.client.force_authenticate(self.bugalter)
        self.assertEqual(self.client.get('/api/configuration-requests/').status_code, 200)
        self.assertEqual(
            self.client.post('/api/configuration-requests/', {'text': 'x'},
                             format='json').status_code, 403,
        )

    def test_complete_requires_configuration(self):
        request_id = self._request()
        self.client.force_authenticate(self.engineer)
        response = self.client.post(
            f'/api/configuration-requests/{request_id}/complete/', {}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('configuration', response.data)
