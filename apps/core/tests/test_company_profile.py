from django.core.exceptions import ValidationError
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.core.models import CompanyProfile


class CompanyProfileTests(APITestCase):
    """Bajaruvchi rekvizitlari: hamma o'qiydi, faqat admin tahrirlaydi, yozuv bitta."""

    def setUp(self):
        self.admin = User.objects.create_user('admin', password='p', role=User.Role.ADMIN)
        self.sales = User.objects.create_user('sales', password='p', role=User.Role.SALES)
        self.bugalter = User.objects.create_user('bugalter', password='p', role=User.Role.BUGALTER)

    def test_first_get_creates_empty_profile(self):
        """Hali to'ldirilmagan bo'lsa ham GET 200 — bo'sh rekvizitlar qaytadi."""
        self.client.force_authenticate(self.sales)
        response = self.client.get('/api/company/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], '')
        self.assertEqual(CompanyProfile.objects.count(), 1)

    def test_admin_fills_profile_and_everyone_reads(self):
        self.client.force_authenticate(self.admin)
        response = self.client.put('/api/company/', {
            'name': 'Swiftcore MCHJ',
            'inn': '305123456',
            'phone': '+998911198877',
            'email': 'swiftcore@gmail.com',
            'address': 'Toshkent shahri, Yunusobod tumani',
            'bank_name': 'Kapitalbank',
            'mfo': '01088',
            'account_number': '20208000900000000001',
            'director_name': 'Karimov A.',
            'contract_terms': "To'lov 30% oldindan.",
        })
        self.assertEqual(response.status_code, 200, response.data)

        self.client.force_authenticate(self.bugalter)
        response = self.client.get('/api/company/')
        self.assertEqual(response.data['name'], 'Swiftcore MCHJ')
        self.assertEqual(response.data['inn'], '305123456')

    def test_only_admin_writes(self):
        for user in (self.sales, self.bugalter):
            self.client.force_authenticate(user)
            response = self.client.patch('/api/company/', {'name': 'Hacker MCHJ'})
            self.assertEqual(response.status_code, 403, user.username)

    def test_singleton_second_row_blocked(self):
        CompanyProfile.load()
        with self.assertRaises(ValidationError):
            CompanyProfile.objects.create(name='Ikkinchi MCHJ')
        self.assertEqual(CompanyProfile.objects.count(), 1)

    def test_patch_updates_single_row(self):
        """PATCH mavjud yagona yozuvni tahrirlaydi, yangisini ochmaydi."""
        self.client.force_authenticate(self.admin)
        self.client.patch('/api/company/', {'name': 'Swiftcore MCHJ'})
        self.client.patch('/api/company/', {'phone': '+998911198877'})
        self.assertEqual(CompanyProfile.objects.count(), 1)
        profile = CompanyProfile.load()
        self.assertEqual(profile.name, 'Swiftcore MCHJ')
        self.assertEqual(profile.phone, '+998911198877')

    def test_markup_and_min_margin_percent_are_patchable(self):
        """28-§8/27-§3: `markup_percent` bu serializerda umuman yo'q edi —
        admin uni hech qachon qo'ya olmagan (frontend forma bo'lsa ham PATCH
        jimgina tashlab ketardi). Endi ikkalasi ham (`min_margin_percent`
        bilan birga, 27-to'plam) tahrirlanadi."""
        self.client.force_authenticate(self.admin)
        response = self.client.patch('/api/company/', {
            'markup_percent': '5', 'min_margin_percent': '10',
        })
        self.assertEqual(response.status_code, 200, response.data)
        profile = CompanyProfile.load()
        self.assertEqual(str(profile.markup_percent), '5.00')
        self.assertEqual(str(profile.min_margin_percent), '10.00')
