from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.inventory.models import Warehouse
from apps.inventory.services import main_warehouse


class SingleWarehouseTests(TestCase):
    """Biznesda BITTA ombor — filial yo'q, ikkinchisi yaratilmaydi."""

    def test_second_warehouse_is_blocked(self):
        Warehouse.objects.create(name='Asosiy ombor')
        with self.assertRaises(ValidationError):
            Warehouse.objects.create(name='Samarqand filiali')
        self.assertEqual(Warehouse.objects.count(), 1)

    def test_existing_warehouse_can_be_edited(self):
        warehouse = Warehouse.objects.create(name='Asosiy ombor')
        warehouse.address = 'Toshkent, Sergeli 7-mavze'
        warehouse.save()
        self.assertEqual(Warehouse.objects.get().address, 'Toshkent, Sergeli 7-mavze')

    def test_main_warehouse_returns_the_single_one(self):
        warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.assertEqual(main_warehouse(), warehouse)

    def test_main_warehouse_creates_when_missing(self):
        """Bo'sh tizimda ham jarayonlar to'xtab qolmaydi — ombor o'zi ochiladi."""
        self.assertEqual(Warehouse.objects.count(), 0)
        warehouse = main_warehouse()
        self.assertEqual(warehouse.name, 'Asosiy ombor')
        self.assertEqual(Warehouse.objects.count(), 1)
