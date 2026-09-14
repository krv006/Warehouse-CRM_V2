from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.inventory.models import Product
from apps.procurement.models import Replenishment, ReplenishmentItem


class PayAmountParsingTests(APITestCase):
    """pay: front summani satr/float qilib yuborsa ham 500 bo'lmaydi.

    Prod'da topilgan xato: {"debt_amount": "500000"} (satr) yuborilganda
    min/max taqqoslash TypeError bilan yiqilib 500 qaytarardi.
    """

    def setUp(self):
        from django.utils.timezone import now

        from apps.finance.services import record_transaction
        from apps.inventory.services import main_warehouse

        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.warehouse = main_warehouse()
        self.component = Product.objects.create(
            sku='GPU-1', name='GPU', cost_price=Decimal('4000000'),
        )
        # Kassada hisobga yetadigan pul bor
        record_transaction(code='ustav_in', amount=Decimal('10000000'), occurred_at=now())
        self.client.force_authenticate(self.bugalter)

    def _make_approved(self):
        replenishment = Replenishment.objects.create(
            warehouse=self.warehouse, status=Replenishment.Status.APPROVED,
            created_by=self.bugalter,
        )
        ReplenishmentItem.objects.create(
            replenishment=replenishment, product=self.component,
            quantity=1, unit_price=Decimal('4000000'), vat_percent=Decimal('12'),
        )
        return replenishment

    def _pay(self, replenishment, body):
        return self.client.post(
            f'/api/replenishments/{replenishment.id}/pay/', body, format='json',
        )

    def test_string_debt_amount_is_accepted(self):
        replenishment = self._make_approved()
        response = self._pay(replenishment, {'debt_amount': '500000'})
        self.assertEqual(response.status_code, 200, response.data)
        replenishment.refresh_from_db()
        self.assertEqual(replenishment.debt.amount, Decimal('500000'))

    def test_empty_string_falls_back_to_auto(self):
        """Bo'sh satr — summa berilmagani kabi: shortfall avtomatik hisoblanadi."""
        replenishment = self._make_approved()
        response = self._pay(replenishment, {'debt_amount': ''})
        self.assertEqual(response.status_code, 200, response.data)

    def test_garbage_debt_amount_is_400_not_500(self):
        replenishment = self._make_approved()
        response = self._pay(replenishment, {'debt_amount': 'abc'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('debt_amount', response.data)
