from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client

INDIVIDUAL = {
    'type': Client.Type.INDIVIDUAL,
    'full_name': 'Kamronbek Rustamov',
    'passport': 'AA1234567',
    'jshshir': '12345678901234',
    'phone': '+998901112233',
}

LEGAL = {
    'type': Client.Type.LEGAL,
    'company_name': 'Ombor Servis MCHJ',
    'inn': '305123456',
    'jshshir': '98765432109876',
    'director_name': 'Aziz Karimov',
    'address': 'Toshkent, Chilonzor 5',
    'phone': '+998901112244',
}


class ClientApiTests(APITestCase):
    """Client 2 xil: jismoniy va yuridik. Bugalter client qo'sha olmaydi."""

    def setUp(self):
        self.sales = User.objects.create_user('sales', password='p', role=User.Role.SALES)
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)

    def test_sales_creates_individual_client(self):
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/clients/', INDIVIDUAL)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['display_name'], 'Kamronbek Rustamov')
        self.assertEqual(Client.objects.get().created_by, self.sales)

    def test_individual_requires_passport_and_jshshir(self):
        self.client.force_authenticate(self.sales)
        payload = dict(INDIVIDUAL)
        payload.pop('passport')
        payload.pop('jshshir')
        response = self.client.post('/api/clients/', payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn('passport', response.data)
        self.assertIn('jshshir', response.data)

    def test_legal_requires_inn_and_address(self):
        self.client.force_authenticate(self.sales)
        payload = dict(LEGAL)
        payload.pop('inn')
        payload.pop('address')
        response = self.client.post('/api/clients/', payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn('inn', response.data)
        self.assertIn('address', response.data)

    def test_phone_is_unique(self):
        self.client.force_authenticate(self.sales)
        self.client.post('/api/clients/', INDIVIDUAL)
        duplicate = dict(LEGAL)
        duplicate['phone'] = INDIVIDUAL['phone']
        response = self.client.post('/api/clients/', duplicate)
        self.assertEqual(response.status_code, 400)
        self.assertIn('phone', response.data)

    def test_bugalter_cannot_create_but_can_read(self):
        self.client.force_authenticate(self.bugalter)
        self.assertEqual(self.client.post('/api/clients/', INDIVIDUAL).status_code, 403)
        self.assertEqual(self.client.get('/api/clients/').status_code, 200)
