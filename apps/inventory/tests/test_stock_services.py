from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.inventory.models import Category, Product, Stock, StockMovement, Warehouse
from apps.inventory.services import apply_movement, available_quantity


def make_product(sku='SSD-1TB', name='SSD 1 TB', kind=Product.Kind.COMPONENT):
    category = Category.objects.get_or_create(name='Butlovchilar')[0]
    return Product.objects.create(sku=sku, name=name, kind=kind, category=category)


class StockServiceTests(TestCase):
    """Kirim, chiqim va tuzatish ombor qoldigini to'g'ri hisoblaydi."""

    def setUp(self):
        self.product = make_product()
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')

    def _move(self, type, quantity):
        return apply_movement(
            product=self.product,
            warehouse=self.warehouse,
            type=type,
            quantity=Decimal(quantity),
        )

    def test_in_increases_stock(self):
        self._move(StockMovement.Type.IN, 10)
        self.assertEqual(available_quantity(self.product), Decimal('10.00'))

    def test_out_decreases_stock(self):
        self._move(StockMovement.Type.IN, 10)
        self._move(StockMovement.Type.OUT, 4)
        self.assertEqual(available_quantity(self.product, self.warehouse), Decimal('6.00'))

    def test_adjust_sets_final_quantity(self):
        self._move(StockMovement.Type.IN, 10)
        self._move(StockMovement.Type.ADJUST, 3)
        self.assertEqual(Stock.objects.get().quantity, Decimal('3.00'))

    def test_low_stock_flag(self):
        self.product.reorder_level = 5
        self.product.save()
        self._move(StockMovement.Type.IN, 2)
        self.assertTrue(self.product.is_low_stock)


class StockMovementApiTests(APITestCase):
    """Movement API orqali qoldiq yangilanadi va created_by yoziladi."""

    def setUp(self):
        self.user = User.objects.create_user('admin', password='p', role=User.Role.ADMIN)
        self.product = make_product(sku='GPU-32', name='GPU 32')
        self.warehouse = Warehouse.objects.create(name='Ombor 1')
        self.client.force_authenticate(self.user)

    def test_create_movement_updates_stock(self):
        response = self.client.post('/api/movements/', {
            'product': self.product.id,
            'warehouse': self.warehouse.id,
            'type': StockMovement.Type.IN,
            'quantity': '7',
        })
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(available_quantity(self.product), Decimal('7.00'))
        self.assertEqual(StockMovement.objects.get().created_by, self.user)
