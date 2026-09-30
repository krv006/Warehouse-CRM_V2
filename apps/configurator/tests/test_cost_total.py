from decimal import Decimal

from django.test import TestCase

from apps.accounts.models import User
from apps.configurator.models import Configuration, ConfigurationItem
from apps.inventory.models import Product, ProductSpec, Warehouse


class ConfigurationCostTotalTests(TestCase):
    """27-§2: `Configuration.cost_total` — qator turiga qarab to'rt xil hisob."""

    def setUp(self):
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')

    def test_build_mode_sums_component_cost_price(self):
        base = Product.objects.create(sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE)
        ram = Product.objects.create(
            sku='RAM-16', name='RAM 16', kind=Product.Kind.COMPONENT, cost_price=Decimal('500000'),
        )
        ssd = Product.objects.create(
            sku='SSD-1TB', name='SSD 1TB', kind=Product.Kind.COMPONENT, cost_price=Decimal('700000'),
        )
        configuration = Configuration.objects.create(
            base_product=base, warehouse=self.warehouse, created_by=self.engineer,
            mode=Configuration.Mode.BUILD,
        )
        ConfigurationItem.objects.create(configuration=configuration, component=ram, label='RAM', quantity=2)
        ConfigurationItem.objects.create(configuration=configuration, component=ssd, label='SSD', quantity=1)
        self.assertEqual(configuration.cost_total, Decimal('1700000'))
        self.assertTrue(configuration.cost_known)

    def test_build_mode_one_component_without_cost_is_unknown(self):
        base = Product.objects.create(sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE)
        ram = Product.objects.create(
            sku='RAM-16', name='RAM 16', kind=Product.Kind.COMPONENT, cost_price=Decimal('500000'),
        )
        no_cost = Product.objects.create(sku='CABLE-1', name='Kabel', kind=Product.Kind.COMPONENT)
        configuration = Configuration.objects.create(
            base_product=base, warehouse=self.warehouse, created_by=self.engineer,
            mode=Configuration.Mode.BUILD,
        )
        ConfigurationItem.objects.create(configuration=configuration, component=ram, label='RAM', quantity=1)
        ConfigurationItem.objects.create(configuration=configuration, component=no_cost, label='Kabel', quantity=1)
        self.assertFalse(configuration.cost_known)

    def test_order_mode_uses_base_product_cost(self):
        base = Product.objects.create(
            sku='DELL-3680', name='Dell', kind=Product.Kind.MACHINE, cost_price=Decimal('18000000'),
        )
        configuration = Configuration.objects.create(
            base_product=base, warehouse=self.warehouse, created_by=self.engineer,
            mode=Configuration.Mode.ORDER,
        )
        self.assertEqual(configuration.cost_total, Decimal('18000000'))
        self.assertTrue(configuration.cost_known)

    def test_order_mode_without_cost_is_unknown(self):
        base = Product.objects.create(sku='DELL-3680', name='Dell', kind=Product.Kind.MACHINE)
        configuration = Configuration.objects.create(
            base_product=base, warehouse=self.warehouse, created_by=self.engineer,
            mode=Configuration.Mode.ORDER,
        )
        self.assertEqual(configuration.cost_total, 0)
        self.assertFalse(configuration.cost_known)

    def test_modify_mode_adds_and_subtracts_changes(self):
        base = Product.objects.create(
            sku='HP-990', name='HP 990', kind=Product.Kind.MACHINE, cost_price=Decimal('10000000'),
        )
        old_ram = Product.objects.create(
            sku='RAM-8', name='RAM 8', kind=Product.Kind.COMPONENT, cost_price=Decimal('300000'),
        )
        new_ram = Product.objects.create(
            sku='RAM-32', name='RAM 32', kind=Product.Kind.COMPONENT, cost_price=Decimal('900000'),
        )
        ProductSpec.objects.create(product=base, component=old_ram, label='RAM', quantity=1)
        configuration = Configuration.objects.create(
            base_product=base, warehouse=self.warehouse, created_by=self.engineer,
            mode=Configuration.Mode.MODIFY,
        )
        # Zavod RAM'i yechildi, kattarog'i qo'shildi
        ConfigurationItem.objects.create(configuration=configuration, component=new_ram, label='RAM', quantity=1)
        # Tannarx: 10 000 000 (baza) + 900 000 (qo'shilgan) - 300 000 (yechilgan)
        self.assertEqual(configuration.cost_total, Decimal('10600000'))
        self.assertTrue(configuration.cost_known)
