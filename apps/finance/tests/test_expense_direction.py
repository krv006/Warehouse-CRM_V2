from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.finance.models import CashCategory
from apps.finance.services import ensure_default_categories


class ExpenseDirectionTests(APITestCase):
    """§10.12.1: xarajat so'rovi faqat chiqim yacheykasiga yoziladi.

    Kirim yacheykasi tanlansa, tasdiqda kassaga chiqim o'rniga kirim
    yozilib qoldiq buzilardi.
    """

    def setUp(self):
        ensure_default_categories()
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.client.force_authenticate(self.bugalter)

    def _request(self, code):
        category = CashCategory.objects.get(code=code)
        return self.client.post('/api/expense-requests/', {
            'category': category.id,
            'amount': '500000',
            'purpose': 'Ofis xarajati',
        }, format='json')

    def test_income_category_is_rejected(self):
        response = self._request('sale')
        self.assertEqual(response.status_code, 400)
        self.assertIn('category', response.data)

    def test_expense_category_is_accepted(self):
        response = self._request('rent')
        self.assertEqual(response.status_code, 201, response.data)
