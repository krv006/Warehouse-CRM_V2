from decimal import Decimal

from django.utils.timezone import now

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.finance.services import record_transaction


class DashboardRoleTests(APITestCase):
    """§10.4: dashboard'dagi kassa bloki faqat admin va bugalterga."""

    def setUp(self):
        record_transaction(code='ustav_in', amount=Decimal('1000000'), occurred_at=now())

    def _dashboard_as(self, role):
        user = User.objects.create_user(f'u_{role}', password='p', role=role)
        self.client.force_authenticate(user)
        return self.client.get('/api/dashboard/')

    def test_cash_block_hidden_from_sales_and_supplier(self):
        for role in (User.Role.SALES, User.Role.SUPPLIER, User.Role.ENGINEER):
            response = self._dashboard_as(role)
            self.assertEqual(response.status_code, 200)
            self.assertIsNone(response.data['kassa'], f'{role} kassani ko\'rmasligi kerak')

    def test_cash_block_visible_to_finance_roles(self):
        for role in (User.Role.ADMIN, User.Role.BUGALTER):
            response = self._dashboard_as(role)
            self.assertEqual(
                response.data['kassa']['balance'], Decimal('1000000'),
            )
