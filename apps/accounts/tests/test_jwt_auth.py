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
