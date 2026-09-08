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
    'mfo': '00423',
    'bank_name': 'Ipoteka Bank',
    'account_number': '20208000600123456001',
    'director_name': 'Aziz Karimov',
    'address': 'Toshkent, Chilonzor 5',
    'phone': '+998901112244',
}


class ClientApiTests(APITestCase):
    """Client 2 xil: jismoniy va yuridik. Bugalter client qo'sha olmaydi."""

    def setUp(self):
        self.sales = User.objects.create_user('sales', password='p', role=User.Role.SALES)
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)

    def test_empty_unique_fields_do_not_clash(self):
        """500 regressiyasi: front bo'sh inputni "" yuboradi — ikkita mijozda ham.

        unique+null maydonlarda "" NULL ga aylanadi, aks holda ikkinchi mijoz
        IntegrityError (500) berardi.
        """
        self.client.force_authenticate(self.sales)
        first = {**INDIVIDUAL, 'account_number': '', 'company_name': '', 'inn': ''}
        response = self.client.post('/api/clients/', first, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIsNone(response.data['account_number'])

        second = {
            **INDIVIDUAL,
            'full_name': 'Ikkinchi Mijoz', 'passport': 'BB7654321',
            'jshshir': '43210987654321', 'phone': '+998901112255',
            'account_number': '', 'company_name': '', 'inn': '',
        }
        response = self.client.post('/api/clients/', second, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Client.objects.count(), 2)

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

    def test_legal_requires_inn_and_bank_details(self):
        """TZ 10.2: INN, MFO, bank nomi va hisob raqam majburiy."""
        self.client.force_authenticate(self.sales)
        payload = dict(LEGAL)
        for field in ['inn', 'mfo', 'bank_name', 'account_number']:
            payload.pop(field)
        response = self.client.post('/api/clients/', payload)
        self.assertEqual(response.status_code, 400)
        for field in ['inn', 'mfo', 'bank_name', 'account_number']:
            self.assertIn(field, response.data)

    def test_legal_address_is_optional(self):
        """TZ 10.2 da manzil ixtiyoriyga o'tdi."""
        self.client.force_authenticate(self.sales)
        payload = dict(LEGAL)
        payload.pop('address')
        response = self.client.post('/api/clients/', payload)
        self.assertEqual(response.status_code, 201, response.data)

    def test_account_number_is_unique(self):
        self.client.force_authenticate(self.sales)
        self.client.post('/api/clients/', LEGAL)
        duplicate = dict(LEGAL)
        duplicate.update({
            'company_name': 'Boshqa MCHJ', 'inn': '309999999',
            'jshshir': '39999999900001', 'phone': '+998901119999',
        })
        response = self.client.post('/api/clients/', duplicate)
        self.assertEqual(response.status_code, 400)
        self.assertIn('account_number', response.data)

    def test_phone_is_unique(self):
        self.client.force_authenticate(self.sales)
        self.client.post('/api/clients/', INDIVIDUAL)
        duplicate = dict(LEGAL)
        duplicate['phone'] = INDIVIDUAL['phone']
        response = self.client.post('/api/clients/', duplicate)
        self.assertEqual(response.status_code, 400)
        self.assertIn('phone', response.data)

    def test_supplier_can_create_client(self):
        """TZ 11: client qo'shish Sales va Buyurtmachida bor."""
        supplier = User.objects.create_user('buyurtmachi', password='p', role=User.Role.SUPPLIER)
        self.client.force_authenticate(supplier)
        self.assertEqual(self.client.post('/api/clients/', INDIVIDUAL).status_code, 201)

    def test_bugalter_cannot_create_but_can_read(self):
        self.client.force_authenticate(self.bugalter)
        self.assertEqual(self.client.post('/api/clients/', INDIVIDUAL).status_code, 403)
        self.assertEqual(self.client.get('/api/clients/').status_code, 200)
