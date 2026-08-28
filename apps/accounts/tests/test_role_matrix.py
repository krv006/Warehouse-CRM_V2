from rest_framework.test import APITestCase

from apps.accounts.models import User

# TZ 8: har bir rol qaysi bo'limni ko'radi (GET 200) va qaysisini ko'rmaydi (403)
ALL = {'admin', 'bugalter', 'sales', 'buyurtmachi', 'engineer'}

READ_MATRIX = {
    '/api/dashboard/': ALL,
    '/api/clients/': ALL,
    '/api/leads/': ALL,
    '/api/contracts/': ALL,
    '/api/configurations/': ALL,
    '/api/acts/': ALL,
    '/api/products/': ALL,
    '/api/stocks/': ALL,

    # TZ 8.3: sales bu bo'limlarni umuman ko'rmaydi
    '/api/cash-transactions/': {'admin', 'bugalter'},
    '/api/loans/': {'admin', 'bugalter'},
    '/api/expense-requests/': {'admin', 'bugalter'},
    '/api/purchases/': {'admin', 'bugalter', 'buyurtmachi'},
    '/api/replenishments/': {'admin', 'bugalter', 'buyurtmachi'},
    '/api/configuration-requests/': ALL,

    # Faqat admin
    '/api/users/': {'admin'},
    '/api/activity-logs/': {'admin'},
}

# Yozish (POST) ruxsati: bo'sh ma'lumot yuboriladi, 403 bo'lmasa ruxsat bor demak
WRITE_MATRIX = {
    '/api/clients/': {'admin', 'sales', 'buyurtmachi'},
    '/api/leads/': {'admin', 'sales'},
    '/api/contracts/': {'admin', 'sales'},
    '/api/configurations/': {'admin', 'engineer'},
    '/api/acts/': {'admin', 'sales'},
    '/api/cash-transactions/': {'admin', 'bugalter'},
    '/api/loans/': {'admin', 'bugalter'},
    '/api/purchases/': {'admin', 'bugalter'},
    '/api/replenishments/': {'admin', 'buyurtmachi'},
}


class RoleMatrixTests(APITestCase):
    """TZ 8: har bir rol aynan o'z bo'limini ko'radi, begonasini emas."""

    def setUp(self):
        self.users = {
            'admin': User.objects.create_user('a', password='p', role=User.Role.ADMIN),
            'bugalter': User.objects.create_user('b', password='p', role=User.Role.BUGALTER),
            'sales': User.objects.create_user('s', password='p', role=User.Role.SALES),
            'buyurtmachi': User.objects.create_user('q', password='p', role=User.Role.SUPPLIER),
            'engineer': User.objects.create_user('e', password='p', role=User.Role.ENGINEER),
        }

    def test_read_access(self):
        for url, allowed in READ_MATRIX.items():
            for role, user in self.users.items():
                with self.subTest(url=url, role=role):
                    self.client.force_authenticate(user)
                    status = self.client.get(url).status_code
                    if role in allowed:
                        self.assertEqual(status, 200, f'{role} {url} ni ko\'ra olishi kerak')
                    else:
                        self.assertEqual(status, 403, f'{role} {url} ni ko\'rmasligi kerak')

    def test_write_access(self):
        for url, allowed in WRITE_MATRIX.items():
            for role, user in self.users.items():
                with self.subTest(url=url, role=role):
                    self.client.force_authenticate(user)
                    status = self.client.post(url, {}, format='json').status_code
                    if role in allowed:
                        self.assertNotEqual(status, 403, f'{role} {url} ga yoza olishi kerak')
                    else:
                        self.assertEqual(status, 403, f'{role} {url} ga yoza olmasligi kerak')

    def test_sales_cannot_touch_money_sections(self):
        """Alohida tekshiruv: sales uchun pul bo'limlari butunlay yopiq."""
        self.client.force_authenticate(self.users['sales'])
        for url in ['/api/cash-transactions/', '/api/cash-transactions/summary/',
                    '/api/loans/', '/api/expense-requests/', '/api/cash-categories/']:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_catalog_is_read_only_for_everyone(self):
        """TZ da alohida "mahsulot qo'shish" yo'q — katalog faqat o'qish uchun.

        Yangi mahsulot Buyurtmachi to'ldirish buyurtmasiga qator qo'shganda
        paydo bo'ladi (TZ 7), ombor qoldig'i esa Kirim/Chiqim orqali o'zgaradi.
        """
        for role, user in self.users.items():
            self.client.force_authenticate(user)
            for url in ['/api/products/', '/api/stocks/', '/api/movements/',
                        '/api/warehouses/', '/api/product-specs/']:
                with self.subTest(role=role, url=url):
                    self.assertEqual(self.client.get(url).status_code, 200)
                    self.assertEqual(
                        self.client.post(url, {}, format='json').status_code, 405,
                        f"{url} yozish uchun ochiq bo'lmasligi kerak",
                    )


    def test_sales_cannot_write_configurations_anymore(self):
        """Configurator ishlari Engineerga o'tdi — sales endi yoza olmaydi."""
        self.client.force_authenticate(self.users['sales'])
        self.assertEqual(
            self.client.post('/api/configurations/', {}, format='json').status_code, 403,
        )
        # lekin zayavka yubora oladi
        self.assertNotEqual(
            self.client.post('/api/configuration-requests/', {}, format='json').status_code, 403,
        )
