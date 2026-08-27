from datetime import timedelta
from decimal import Decimal

from django.utils.timezone import localdate
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.finance.models import CashTransaction
from apps.inventory.models import Product, Warehouse
from apps.inventory.services import available_quantity
from apps.purchases.models import Purchase, PurchaseItem


class PurchaseFlowTests(APITestCase):
    """Kirim 3 xil: UZB ichidan, import va ustav."""

    def setUp(self):
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.sales = User.objects.create_user('sales', password='p', role=User.Role.SALES)
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.product = Product.objects.create(sku='GPU-32', name='GPU 32')
        self.client.force_authenticate(self.bugalter)

    def _purchase(self, type=Purchase.Type.LOCAL, **kwargs):
        purchase = Purchase.objects.create(
            type=type, supplier='Etuf MCHJ', warehouse=self.warehouse, **kwargs,
        )
        PurchaseItem.objects.create(
            purchase=purchase, product=self.product,
            quantity=Decimal('3'), unit_price=Decimal('4000000'),
        )
        return purchase

    def test_number_generated(self):
        self.assertTrue(self._purchase().number.startswith('KIR-'))

    def test_total_includes_customs_and_tax(self):
        purchase = self._purchase(
            type=Purchase.Type.USTAV,
            customs_duty=Decimal('500000'),
            tax_amount=Decimal('300000'),
        )
        self.assertEqual(purchase.items_total, Decimal('12000000'))
        self.assertEqual(purchase.total_amount, Decimal('12800000'))

    def test_expected_date_from_lead_days(self):
        ordered = localdate()
        purchase = self._purchase(
            type=Purchase.Type.IMPORT, lead_days=90, ordered_at=ordered,
            status=Purchase.Status.IN_TRANSIT,
        )
        self.assertEqual(purchase.expected_at, ordered + timedelta(days=90))
        self.assertEqual(purchase.days_left, 90)
        self.assertEqual(purchase.color, 'green')

    def test_receive_updates_stock_and_kassa(self):
        purchase = self._purchase(type=Purchase.Type.IMPORT, lead_days=30)
        response = self.client.post(f'/api/purchases/{purchase.id}/receive/')
        self.assertEqual(response.status_code, 200, response.data)

        purchase.refresh_from_db()
        self.assertEqual(purchase.status, Purchase.Status.RECEIVED)
        self.assertEqual(purchase.received_at, localdate())
        self.assertEqual(available_quantity(self.product, self.warehouse), Decimal('3.00'))

        transaction = CashTransaction.objects.get()
        self.assertEqual(transaction.category.code, 'import')
        self.assertEqual(transaction.amount, purchase.total_amount)

    def test_double_receive_is_rejected(self):
        purchase = self._purchase()
        self.client.post(f'/api/purchases/{purchase.id}/receive/')
        response = self.client.post(f'/api/purchases/{purchase.id}/receive/')
        self.assertEqual(response.status_code, 400)

    def test_in_transit_list(self):
        self._purchase(
            type=Purchase.Type.IMPORT, lead_days=90, ordered_at=localdate(),
            status=Purchase.Status.IN_TRANSIT,
        )
        response = self.client.get('/api/purchases/in-transit/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['days_left'], 90)

    def test_sales_cannot_create_purchase(self):
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/purchases/', {
            'type': Purchase.Type.LOCAL,
            'supplier': 'Test',
            'warehouse': self.warehouse.id,
            'items': [],
        }, format='json')
        self.assertEqual(response.status_code, 403)
