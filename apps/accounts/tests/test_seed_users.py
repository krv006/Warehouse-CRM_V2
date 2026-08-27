from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.accounts.models import User


class SeedUsersTests(TestCase):
    """seed_users komandasi har bir rolga foydalanuvchi ochadi."""

    def _run(self, **options):
        out = StringIO()
        call_command('seed_users', stdout=out, **options)
        return out.getvalue()

    def test_creates_user_for_each_role(self):
        self._run()
        self.assertEqual(User.objects.count(), 6)
        self.assertEqual(User.objects.get(username='buyurtmachi').role, User.Role.SUPPLIER)
        self.assertEqual(User.objects.get(username='engineer').role, User.Role.ENGINEER)
        self.assertEqual(User.objects.get(username='admin').role, User.Role.ADMIN)
        self.assertEqual(User.objects.get(username='bugalter').role, User.Role.BUGALTER)
        self.assertEqual(User.objects.get(username='sales1').role, User.Role.SALES)
        self.assertEqual(User.objects.get(username='sales2').role, User.Role.SALES)

    def test_admin_is_superuser(self):
        self._run()
        admin = User.objects.get(username='admin')
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_admin)

    def test_password_is_usable(self):
        self._run(password='Sinov12345')
        self.assertTrue(User.objects.get(username='sales1').check_password('Sinov12345'))

    def test_second_run_does_not_duplicate_or_reset(self):
        self._run(password='Birinchi123')
        self._run(password='Ikkinchi123')
        self.assertEqual(User.objects.count(), 6)
        # --force siz mavjud parol saqlanadi
        self.assertTrue(User.objects.get(username='admin').check_password('Birinchi123'))

    def test_force_resets_password(self):
        self._run(password='Birinchi123')
        self._run(password='Ikkinchi123', force=True)
        self.assertEqual(User.objects.count(), 6)
        self.assertTrue(User.objects.get(username='admin').check_password('Ikkinchi123'))

    def test_users_can_login_through_api(self):
        self._run()
        response = self.client.post('/api/auth/login/', {
            'username': 'bugalter',
            'password': 'Ombor2026!',
        })
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn('access', response.data)
