from datetime import timedelta
from decimal import Decimal

from django.utils.timezone import localdate, now
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.core.utils import RED, YELLOW
from apps.finance.models import CashTransaction, Loan
from apps.finance.services import ensure_default_categories, record_transaction
from apps.inventory.models import Category, Product, StockMovement, Warehouse
from apps.inventory.services import apply_movement, available_quantity
from apps.procurement.models import Replenishment, ReplenishmentEvent, ReplenishmentItem


class ReplenishmentFlowTests(APITestCase):
    """TZ 7: buyurtmachi -> bugalter -> admin -> to'lov -> ombor."""

    def setUp(self):
        ensure_default_categories()
        self.supplier = User.objects.create_user('buyurtmachi', password='p', role=User.Role.SUPPLIER)
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.admin = User.objects.create_user('admin', password='p', role=User.Role.ADMIN)
        self.sales = User.objects.create_user('sales', password='p', role=User.Role.SALES)

        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        category = Category.objects.create(name='Butlovchilar')
        self.product = Product.objects.create(
            sku='GPU-32', name='GPU 32', category=category,
            reorder_level=10, cost_price=Decimal('400000'),
        )
        self.client.force_authenticate(self.supplier)

    def _cash(self, amount):
        record_transaction(code='sale', amount=Decimal(amount), occurred_at=now())

    def _replenishment(self, quantity='5', price='200000', **kwargs):
        replenishment = Replenishment.objects.create(
            warehouse=self.warehouse, supplier='Etuf MCHJ',
            created_by=self.supplier, **kwargs,
        )
        ReplenishmentItem.objects.create(
            replenishment=replenishment, product=self.product,
            quantity=Decimal(quantity), unit_price=Decimal(price),
        )
        return replenishment

    def test_number_is_generated(self):
        self.assertTrue(self._replenishment().number.startswith('TLD-'))

    def test_low_stock_list(self):
        response = self.client.get('/api/replenishments/low-stock/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]['sku'], 'GPU-32')
        self.assertEqual(response.data[0]['needed'], 10)

    def test_build_from_low_stock(self):
        response = self.client.post('/api/replenishments/from-low-stock/', {
            'warehouse': self.warehouse.id,
            'supplier': 'Etuf MCHJ',
        })
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data['items']), 1)
        self.assertEqual(response.data['status'], Replenishment.Status.DRAFT)

    def test_total_includes_logistics_and_other(self):
        replenishment = self._replenishment(
            logistics_cost=Decimal('150000'), other_cost=Decimal('50000'),
        )
        self.assertEqual(replenishment.items_total, Decimal('1000000'))
        self.assertEqual(replenishment.total_amount, Decimal('1200000'))

    def test_submit_requires_prices(self):
        replenishment = self._replenishment(price='0')
        response = self.client.post(f'/api/replenishments/{replenishment.id}/submit/')
        self.assertEqual(response.status_code, 400)

    def test_full_approval_chain(self):
        replenishment = self._replenishment()

        response = self.client.post(f'/api/replenishments/{replenishment.id}/submit/')
        self.assertEqual(response.data['status'], Replenishment.Status.PENDING_BUGALTER)

        self.client.force_authenticate(self.bugalter)
        response = self.client.post(f'/api/replenishments/{replenishment.id}/approve/')
        self.assertEqual(response.data['status'], Replenishment.Status.PENDING_ADMIN)

        # Bugalter admin bosqichini o'tolmaydi
        self.assertEqual(
            self.client.post(f'/api/replenishments/{replenishment.id}/approve/').status_code, 403,
        )

        self.client.force_authenticate(self.admin)
        response = self.client.post(f'/api/replenishments/{replenishment.id}/approve/')
        self.assertEqual(response.data['status'], Replenishment.Status.APPROVED)

    def test_sales_cannot_create(self):
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/replenishments/', {
            'warehouse': self.warehouse.id, 'supplier': 'Test',
        })
        self.assertEqual(response.status_code, 403)

    def test_payment_with_enough_cash(self):
        self._cash('5000000')
        replenishment = self._replenishment()
        replenishment.status = Replenishment.Status.APPROVED
        replenishment.save()

        self.client.force_authenticate(self.bugalter)
        response = self.client.post(f'/api/replenishments/{replenishment.id}/pay/')
        self.assertEqual(response.status_code, 200, response.data)

        replenishment.refresh_from_db()
        self.assertEqual(replenishment.status, Replenishment.Status.ORDERED)
        self.assertEqual(replenishment.paid_amount, Decimal('1000000'))
        self.assertIsNone(replenishment.debt)

    def test_shortfall_goes_to_debt(self):
        """TZ 7.1 misoli: summa 1 400 000, kassada 500 000 -> 900 000 qarzga."""
        self._cash('500000')
        replenishment = self._replenishment(quantity='7', price='200000')
        self.assertEqual(replenishment.total_amount, Decimal('1400000'))
        self.assertEqual(replenishment.cash_available, Decimal('500000'))
        self.assertEqual(replenishment.shortfall, Decimal('900000'))

        replenishment.status = Replenishment.Status.APPROVED
        replenishment.save()

        self.client.force_authenticate(self.bugalter)
        response = self.client.post(f'/api/replenishments/{replenishment.id}/pay/')
        self.assertEqual(response.status_code, 200, response.data)

        replenishment.refresh_from_db()
        self.assertEqual(replenishment.paid_amount, Decimal('500000'))
        self.assertEqual(replenishment.debt.amount, Decimal('900000'))
        self.assertEqual(replenishment.debt.source, Loan.Source.SUPPLIER)

    def test_debt_deadline_is_two_months_after_delivery(self):
        self._cash('500000')
        replenishment = self._replenishment(quantity='7', price='200000')
        replenishment.status = Replenishment.Status.APPROVED
        replenishment.save()

        self.client.force_authenticate(self.bugalter)
        self.client.post(f'/api/replenishments/{replenishment.id}/pay/')
        self.client.post(f'/api/replenishments/{replenishment.id}/receive/')

        replenishment.refresh_from_db()
        self.assertEqual(replenishment.delivered_at, localdate())
        self.assertEqual(replenishment.debt.taken_at, localdate())
        self.assertEqual(replenishment.debt.deadline, localdate() + timedelta(days=60))
        self.assertEqual(replenishment.debt_days_left, 60)

    def test_receive_updates_stock(self):
        self._cash('5000000')
        replenishment = self._replenishment()
        replenishment.status = Replenishment.Status.APPROVED
        replenishment.save()

        self.client.force_authenticate(self.bugalter)
        self.client.post(f'/api/replenishments/{replenishment.id}/pay/')
        response = self.client.post(f'/api/replenishments/{replenishment.id}/receive/')
        self.assertEqual(response.status_code, 200, response.data)

        self.assertEqual(available_quantity(self.product, self.warehouse), Decimal('5.00'))
        replenishment.refresh_from_db()
        self.assertEqual(replenishment.status, Replenishment.Status.DELIVERED)

    def test_delivery_stages_are_tracked(self):
        """TZ 7.3: bojxona va boshqa bosqichlar ko'rinib turadi."""
        replenishment = self._replenishment()
        replenishment.status = Replenishment.Status.ORDERED
        replenishment.save()

        response = self.client.post(f'/api/replenishments/{replenishment.id}/events/', {
            'stage': ReplenishmentEvent.Stage.CUSTOMS,
            'comment': 'Bojxonada rasmiylashtirilmoqda',
        })
        self.assertEqual(response.status_code, 200, response.data)
        replenishment.refresh_from_db()
        self.assertEqual(replenishment.status, Replenishment.Status.CUSTOMS)

        response = self.client.get(f'/api/replenishments/{replenishment.id}/timeline/')
        self.assertEqual(len(response.data['events']), 1)

    def test_admin_can_edit_item_after_submit_but_supplier_cannot(self):
        """TZ 7.1: admin miqdorni o'zgartira va pozitsiyani o'chira oladi."""
        replenishment = self._replenishment()
        item = replenishment.items.first()
        self.client.post(f'/api/replenishments/{replenishment.id}/submit/')

        response = self.client.patch(f'/api/replenishment-items/{item.id}/', {'quantity': '3'})
        self.assertEqual(response.status_code, 403)

        self.client.force_authenticate(self.admin)
        response = self.client.patch(f'/api/replenishment-items/{item.id}/', {'quantity': '3'})
        self.assertEqual(response.status_code, 200, response.data)

        response = self.client.delete(f'/api/replenishment-items/{item.id}/')
        self.assertEqual(response.status_code, 204)

    def test_reject_returns_to_supplier(self):
        replenishment = self._replenishment()
        self.client.post(f'/api/replenishments/{replenishment.id}/submit/')

        self.client.force_authenticate(self.bugalter)
        response = self.client.post(
            f'/api/replenishments/{replenishment.id}/reject/', {'comment': 'Narxlar yuqori'},
        )
        self.assertEqual(response.data['status'], Replenishment.Status.REJECTED)

    def test_debt_colors_follow_contract_rules(self):
        self._cash('0')
        replenishment = self._replenishment(quantity='7', price='200000')
        replenishment.status = Replenishment.Status.APPROVED
        replenishment.save()

        self.client.force_authenticate(self.bugalter)
        self.client.post(f'/api/replenishments/{replenishment.id}/pay/')
        replenishment.refresh_from_db()

        debt = replenishment.debt
        debt.taken_at = localdate() - timedelta(days=40)
        debt.save()
        self.assertEqual(replenishment.debt_color, YELLOW)

        debt.taken_at = localdate() - timedelta(days=55)
        debt.save()
        self.assertEqual(replenishment.debt_color, RED)
