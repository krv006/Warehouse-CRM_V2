from rest_framework.test import APITestCase

from apps.accounts.models import User


class UserApiTests(APITestCase):
    """Foydalanuvchilar bo'limi faqat adminga ochiq."""

    def setUp(self):
        self.admin = User.objects.create_user(
            'admin', password='parol123', role=User.Role.ADMIN,
        )
        self.sales = User.objects.create_user(
            'sales', password='parol123', role=User.Role.SALES,
        )

    def test_role_properties(self):
        self.assertTrue(self.admin.is_admin)
        self.assertTrue(self.sales.is_sales)
        self.assertFalse(self.sales.is_bugalter)

    def test_default_role_is_sales(self):
        user = User.objects.create_user('yangi', password='parol123')
        self.assertEqual(user.role, User.Role.SALES)

    def test_me_returns_current_user(self):
        self.client.force_authenticate(self.sales)
        response = self.client.get('/api/users/me/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['username'], 'sales')
        self.assertEqual(response.data['role'], User.Role.SALES)

    def test_only_admin_lists_users(self):
        self.client.force_authenticate(self.sales)
        self.assertEqual(self.client.get('/api/users/').status_code, 403)

        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get('/api/users/').status_code, 200)

    def test_admin_creates_user_with_password(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post('/api/users/', {
            'username': 'bugalter',
            'password': 'parol123',
            'role': User.Role.BUGALTER,
        })
        self.assertEqual(response.status_code, 201)
        self.assertTrue(User.objects.get(username='bugalter').check_password('parol123'))
