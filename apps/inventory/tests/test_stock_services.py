from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.inventory.models import Product, Stock, StockMovement, Warehouse
from apps.inventory.services import apply_movement, available_quantity


def make_product(sku='SSD-1TB', name='SSD 1 TB', kind=Product.Kind.COMPONENT):
    return Product.objects.create(sku=sku, name=name, kind=kind)


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


class StockReadOnlyApiTests(APITestCase):
    """Katalog va qoldiq API'da faqat o'qish uchun (TZ 1: qoldiq Kirim/Chiqim orqali)."""

    def setUp(self):
        self.user = User.objects.create_user('admin', password='p', role=User.Role.ADMIN)
        self.product = make_product(sku='GPU-32', name='GPU 32')
        self.warehouse = Warehouse.objects.create(name='Ombor 1')
        self.client.force_authenticate(self.user)

    def test_read_endpoints_work(self):
        for url in ['/api/products/', '/api/stocks/', '/api/movements/', '/api/warehouses/']:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_manual_write_is_not_available(self):
        """Qoldiqni qo'lda o'zgartirish yo'q — faqat jarayonlar orqali."""
        for url in ['/api/products/', '/api/stocks/', '/api/movements/']:
            with self.subTest(url=url):
                self.assertEqual(self.client.post(url, {}, format='json').status_code, 405)

    def test_service_records_movement(self):
        apply_movement(
            product=self.product,
            warehouse=self.warehouse,
            type=StockMovement.Type.IN,
            quantity=Decimal('7'),
            user=self.user,
        )
        self.assertEqual(available_quantity(self.product), Decimal('7.00'))
        movement = StockMovement.objects.get()
        self.assertEqual(movement.created_by, self.user)
