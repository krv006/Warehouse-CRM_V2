from datetime import timedelta
from decimal import Decimal

from django.utils.timezone import localdate, now
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.core.choices import Direction
from apps.finance.models import CashCategory, CashTransaction, ExpenseRequest, Loan
from apps.finance.services import ensure_default_categories, record_transaction


class KassaTests(APITestCase):
    """Kassa: kirim/chiqim nazorati, qarz va admin ruxsati."""

    def setUp(self):
        ensure_default_categories()
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.admin = User.objects.create_user('admin', password='p', role=User.Role.ADMIN)
        self.client.force_authenticate(self.bugalter)

    def test_default_categories_cover_tz(self):
        codes = set(CashCategory.objects.values_list('code', flat=True))
        self.assertTrue({'sale', 'ustav_in', 'loan'} <= codes)
        self.assertTrue({'import', 'contract_invoice', 'salary', 'rent', 'meal'} <= codes)

    def test_direction_comes_from_category(self):
        transaction = record_transaction(
            code='salary', amount=Decimal('5000000'), occurred_at=now(),
        )
        self.assertEqual(transaction.direction, Direction.OUT)

    def test_summary_reports_balance(self):
        record_transaction(code='sale', amount=Decimal('10000000'), occurred_at=now())
        record_transaction(code='rent', amount=Decimal('3000000'), occurred_at=now())
        response = self.client.get('/api/cash-transactions/summary/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['income_total'], Decimal('10000000'))
        self.assertEqual(response.data['expense_total'], Decimal('3000000'))
        self.assertEqual(response.data['balance'], Decimal('7000000'))

    def test_custom_expense_category_can_be_added(self):
        response = self.client.post('/api/cash-categories/', {
            'code': 'transport',
            'name': 'Transport',
            'direction': Direction.OUT,
        })
        self.assertEqual(response.status_code, 201, response.data)

    def test_loan_creates_income_and_tracks_deadline(self):
        response = self.client.post('/api/loans/', {
            'lender_name': 'Bobur aka',
            'amount': '50000000',
            'taken_at': str(localdate()),
            'deadline': str(localdate() + timedelta(days=30)),
        })
        self.assertEqual(response.status_code, 201, response.data)
        loan = Loan.objects.get()
        self.assertEqual(loan.days_left, 30)
        self.assertEqual(CashTransaction.objects.get(loan=loan).category.code, 'loan')

    def test_loan_repay_closes_loan(self):
        loan = Loan.objects.create(
            lender_name='Bobur aka', amount=Decimal('50000000'),
            taken_at=localdate(), deadline=localdate() + timedelta(days=30),
        )
        response = self.client.post(f'/api/loans/{loan.id}/repay/')
        self.assertEqual(response.status_code, 200, response.data)
        loan.refresh_from_db()
        self.assertEqual(loan.status, Loan.Status.CLOSED)
        self.assertEqual(loan.balance, Decimal('0'))

    def test_expense_request_needs_admin_approval(self):
        category = CashCategory.objects.get(code='rent')
        response = self.client.post('/api/expense-requests/', {
            'category': category.id,
            'amount': '4000000',
            'purpose': 'Ofis arendasi',
        })
        self.assertEqual(response.status_code, 201, response.data)
        request_id = response.data['id']
        self.assertEqual(ExpenseRequest.objects.get().requested_by, self.bugalter)

        # Bugalter o'zi tasdiqlay olmaydi
        self.assertEqual(
            self.client.post(f'/api/expense-requests/{request_id}/approve/').status_code, 403,
        )
        self.assertFalse(CashTransaction.objects.exists())

        self.client.force_authenticate(self.admin)
        response = self.client.post(f'/api/expense-requests/{request_id}/approve/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], ExpenseRequest.Status.APPROVED)

        transaction = CashTransaction.objects.get()
        self.assertEqual(transaction.direction, Direction.OUT)
        self.assertEqual(transaction.approved_by, self.admin)

    def test_expense_request_reject(self):
        category = CashCategory.objects.get(code='meal')
        expense_request = ExpenseRequest.objects.create(
            category=category, amount=Decimal('100000'),
            purpose='Obed', requested_by=self.bugalter,
        )
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            f'/api/expense-requests/{expense_request.id}/reject/', {'comment': 'Keyinroq'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], ExpenseRequest.Status.REJECTED)
        self.assertFalse(CashTransaction.objects.exists())
