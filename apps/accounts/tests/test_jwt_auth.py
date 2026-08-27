from datetime import timedelta

from django.conf import settings
from rest_framework.test import APITestCase

from apps.accounts.models import User


class JwtAuthTests(APITestCase):
    """JWT bilan kirish va tokenni yangilash."""

    def setUp(self):
        self.user = User.objects.create_user(
            'sales', password='parol123', role=User.Role.SALES,
        )

    def test_login_returns_token_pair(self):
        response = self.client.post('/api/auth/login/', {
            'username': 'sales',
            'password': 'parol123',
        })
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_wrong_password_is_rejected(self):
        response = self.client.post('/api/auth/login/', {
            'username': 'sales',
            'password': 'notogri',
        })
        self.assertEqual(response.status_code, 401)

    def test_access_token_opens_protected_endpoint(self):
        self.assertEqual(self.client.get('/api/users/me/').status_code, 401)

        access = self.client.post('/api/auth/login/', {
            'username': 'sales',
            'password': 'parol123',
        }).data['access']
        response = self.client.get('/api/users/me/', HTTP_AUTHORIZATION=f'Bearer {access}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['username'], 'sales')

    def test_refresh_rotates_token(self):
        refresh = self.client.post('/api/auth/login/', {
            'username': 'sales',
            'password': 'parol123',
        }).data['refresh']
        response = self.client.post('/api/auth/refresh/', {'refresh': refresh})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn('access', response.data)
        # ROTATE_REFRESH_TOKENS = True — yangi refresh ham qaytadi
        self.assertIn('refresh', response.data)

    def test_lifetimes_from_settings(self):
        self.assertEqual(settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME'], timedelta(hours=12))
        self.assertEqual(settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'], timedelta(days=7))
        self.assertEqual(settings.SIMPLE_JWT['AUTH_HEADER_TYPES'], ('Bearer',))


class DemoUsersLoginTests(APITestCase):
    """seed_users bergan 4 rolning har biri bilan tizimga kirish."""

    ROLES = {
        'admin': User.Role.ADMIN,
        'bugalter': User.Role.BUGALTER,
        'buyurtmachi': User.Role.SUPPLIER,
        'engineer': User.Role.ENGINEER,
        'sales1': User.Role.SALES,
    }

    def setUp(self):
        from io import StringIO

        from django.core.management import call_command

        call_command('seed_users', stdout=StringIO())

    def _login(self, username, password='Ombor2026!'):
        response = self.client.post('/api/auth/login/', {
            'username': username, 'password': password,
        })
        self.assertEqual(response.status_code, 200, f'{username}: {response.data}')
        return response.data['access']

    def test_every_role_can_login_and_read_own_profile(self):
        for username, role in self.ROLES.items():
            with self.subTest(username=username):
                access = self._login(username)
                response = self.client.get(
                    '/api/users/me/', HTTP_AUTHORIZATION=f'Bearer {access}',
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data['username'], username)
                self.assertEqual(response.data['role'], role)

    def test_role_permissions_after_login(self):
        """Har bir rol o'z bo'limiga kira oladi, begonasiga yo'q."""
        checks = [
            ('admin', '/api/activity-logs/', 200),
            ('bugalter', '/api/activity-logs/', 403),
            ('sales1', '/api/activity-logs/', 403),
            ('buyurtmachi', '/api/activity-logs/', 403),
            ('buyurtmachi', '/api/replenishments/', 200),
            ('engineer', '/api/configurations/', 200),
            ('engineer', '/api/cash-transactions/', 403),
            ('sales1', '/api/contracts/', 200),
            ('bugalter', '/api/cash-transactions/', 200),
        ]
        for username, url, expected in checks:
            with self.subTest(user=username, url=url):
                access = self._login(username)
                response = self.client.get(url, HTTP_AUTHORIZATION=f'Bearer {access}')
                self.assertEqual(response.status_code, expected)

    def test_wrong_password_rejected_for_demo_users(self):
        response = self.client.post('/api/auth/login/', {
            'username': 'buyurtmachi', 'password': 'notogri',
        })
        self.assertEqual(response.status_code, 401)
