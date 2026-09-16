from decimal import Decimal

from django.utils.timezone import now

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.core.choices import Direction
from apps.finance.models import CashTransaction, Loan
from apps.finance.services import cash_balance, record_transaction
from apps.inventory.models import Product
from apps.procurement.models import Replenishment, ReplenishmentItem


class SupplierDebtCashTests(APITestCase):
    """TOPSHIRIQ-2 #1: ta'minotchi qarzi kassaga KIRIM bo'lib tushmasin.

    Qarz — majburiyat: pul harakat qilmaydi. Avval 'loan' kirimi yozilib,
    kassada yo'q pul paydo bo'lar va o'sha pulni sarflash mumkin edi.
    """

    def setUp(self):
        from apps.inventory.services import main_warehouse

        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.warehouse = main_warehouse()
        self.gpu = Product.objects.create(sku='GPU-1', name='GPU')
        # Kassada 90 404 900 bor; hisob 113 345 000 — 22 940 100 qarzga o'tadi
        record_transaction(
            code='ustav_in', amount=Decimal('90404900'), occurred_at=now(),
        )
        self.replenishment = Replenishment.objects.create(
            warehouse=self.warehouse, status=Replenishment.Status.APPROVED,
            supplier='Etuf MCHJ', created_by=self.bugalter,
        )
        ReplenishmentItem.objects.create(
            replenishment=self.replenishment, product=self.gpu,
            quantity=1, unit_price=Decimal('113345000'),
        )
        self.client.force_authenticate(self.bugalter)

    def test_pay_with_debt_leaves_single_expense_and_empty_cash(self):
        """Hujjatdagi jonli holat: to'lovdan keyin kassa BO'SH bo'lishi kerak."""
        response = self.client.post(
            f'/api/replenishments/{self.replenishment.id}/pay/',
        )
        self.assertEqual(response.status_code, 200, response.data)

        flow_rows = CashTransaction.objects.filter(replenishment=self.replenishment)
        # Faqat BITTA yozuv — naqd qism chiqimi; fantom kirim yo'q
        self.assertEqual(flow_rows.count(), 1)
        expense = flow_rows.get()
        self.assertEqual(expense.direction, Direction.OUT)
        self.assertEqual(expense.amount, Decimal('90404900'))
        # Kassa aynan naqd qismga kamaydi: 90 404 900 - 90 404 900 = 0
        self.assertEqual(cash_balance(), Decimal('0'))

        self.replenishment.refresh_from_db()
        self.assertEqual(self.replenishment.debt.amount, Decimal('22940100'))

    def test_total_expense_equals_invoice_after_repay(self):
        """Qarz yopilgach jami chiqim = hisob summasi — mol arzon ko'rinmaydi."""
        self.client.post(f'/api/replenishments/{self.replenishment.id}/pay/')
        # Qarzni yopish uchun kassaga haqiqiy pul keladi
        record_transaction(
            code='ustav_in', amount=Decimal('30000000'), occurred_at=now(),
        )
        self.replenishment.refresh_from_db()
        loan = self.replenishment.debt
        response = self.client.post(f'/api/loans/{loan.id}/repay/')
        self.assertEqual(response.status_code, 200, response.data)

        total_out = (
            CashTransaction.objects.filter(direction=Direction.OUT)
            .aggregate(t=__import__('django').db.models.Sum('amount'))['t']
        )
        self.assertEqual(total_out, Decimal('113345000'))
        loan.refresh_from_db()
        self.assertEqual(loan.status, Loan.Status.CLOSED)
        self.assertEqual(loan.balance, Decimal('0'))

    def test_personal_loan_still_writes_income(self):
        """Shaxsiy qarz — pul haqiqatan keladi, kirim yoziladi."""
        response = self.client.post('/api/loans/', {
            'lender_name': 'Bobur aka', 'amount': '5000000',
            'taken_at': '2026-09-16', 'deadline': '2026-11-16',
            'source': 'personal',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(
            CashTransaction.objects.filter(
                loan_id=response.data['id'], direction=Direction.IN,
            ).exists()
        )

    def test_manual_supplier_loan_writes_no_income(self):
        """Qo'lda ochilgan ta'minotchi qarzi ham kirim yozmaydi."""
        before = cash_balance()
        response = self.client.post('/api/loans/', {
            'lender_name': 'Etuf MCHJ', 'amount': '5000000',
            'taken_at': '2026-09-16', 'deadline': '2026-11-16',
            'source': 'supplier',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(
            CashTransaction.objects.filter(loan_id=response.data['id']).exists()
        )
        self.assertEqual(cash_balance(), before)
