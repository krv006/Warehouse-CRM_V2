from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.inventory.models import Product, StockMovement, Warehouse
from apps.inventory.services import apply_movement, available_quantity


class SeedStockTests(TestCase):
    """seed_stock: kam qolgan mahsulotlar demo kirim bilan to'ldiriladi."""

    def setUp(self):
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.empty = Product.objects.create(sku='HP-880', name='HP 880')
        self.low = Product.objects.create(sku='GPU-32', name='GPU 32', reorder_level=8)
        apply_movement(
            product=self.low, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('2'),
        )
        self.full = Product.objects.create(sku='SSD-1TB', name='SSD 1 TB')
        apply_movement(
            product=self.full, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('17'),
        )

    def test_tops_up_to_target(self):
        call_command('seed_stock', stdout=StringIO())
        self.assertEqual(available_quantity(self.empty, self.warehouse), Decimal('10'))
        # reorder_level 8 -> maqsad 16 (2 barobar)
        self.assertEqual(available_quantity(self.low, self.warehouse), Decimal('16'))
        # yetarlisiga tegilmaydi
        self.assertEqual(available_quantity(self.full, self.warehouse), Decimal('17'))

    def test_idempotent(self):
        call_command('seed_stock', stdout=StringIO())
        before = StockMovement.objects.count()
        call_command('seed_stock', stdout=StringIO())
        self.assertEqual(StockMovement.objects.count(), before)
        self.assertEqual(available_quantity(self.empty, self.warehouse), Decimal('10'))
