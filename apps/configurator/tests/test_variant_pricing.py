from datetime import date
from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.configurator.models import Act, Configuration, ConfigurationItem
from apps.inventory.models import Category, Product


class VariantPricingTests(APITestCase):
    """TZ 6.2: narx ombordan olinadi, tayyor variant tanib olinadi."""

    def setUp(self):
        self.admin = User.objects.create_user('admin', password='p', role=User.Role.ADMIN)
        self.sales = User.objects.create_user('sales', password='p', role=User.Role.SALES)
        self.category = Category.objects.create(name='Kompyuter')
        self.base = Product.objects.create(
            sku='HP-880', name='HP 880', category=self.category, kind=Product.Kind.MACHINE,
        )
        self.ssd = Product.objects.create(
            sku='SSD-1TB', name='SSD 1 TB', category=self.category,
            kind=Product.Kind.COMPONENT, sale_price=Decimal('1500000'),
        )
        self.gpu = Product.objects.create(
            sku='GPU-32', name='GPU 32', category=self.category,
            kind=Product.Kind.COMPONENT, cost_price=Decimal('4000000'),
        )
        self.no_price = Product.objects.create(
            sku='RAM-4', name='RAM 4', category=self.category, kind=Product.Kind.COMPONENT,
        )
        self.act = Act.objects.create(number='ACT-001', title='ACT', issued_at=date.today())
        self.client.force_authenticate(self.sales)

    def _configuration(self, components, act=True):
        configuration = Configuration.objects.create(
            base_product=self.base, created_by=self.sales, act=self.act if act else None,
        )
        for component, quantity in components:
            ConfigurationItem.objects.create(
                configuration=configuration, component=component, quantity=quantity,
            )
        return configuration

    def test_price_taken_from_stock_sale_price(self):
        configuration = self._configuration([(self.ssd, 1)])
        self.assertEqual(configuration.items.first().unit_price, Decimal('1500000'))

    def test_price_falls_back_to_cost_price(self):
        configuration = self._configuration([(self.gpu, 1)])
        self.assertEqual(configuration.items.first().unit_price, Decimal('4000000'))

    def test_component_without_price_is_flagged(self):
        configuration = self._configuration([(self.no_price, 1)])
        item = configuration.items.first()
        self.assertTrue(item.needs_price)
        self.assertEqual(len(configuration.items_without_price), 1)

    def test_finalize_blocked_without_price(self):
        configuration = self._configuration([(self.ssd, 1), (self.no_price, 1)])
        response = self.client.post(f'/api/configurations/{configuration.id}/finalize/')
        self.assertEqual(response.status_code, 400)
        self.assertIn('RAM 4', response.data['items'])

    def test_finalize_creates_reusable_variant(self):
        configuration = self._configuration([(self.ssd, 1), (self.gpu, 1)])
        response = self.client.post(f'/api/configurations/{configuration.id}/finalize/')
        self.assertEqual(response.status_code, 200, response.data)

        configuration.refresh_from_db()
        variant = configuration.variant
        self.assertIsNotNone(variant)
        self.assertEqual(variant.base_model, self.base)
        self.assertEqual(variant.sale_price, Decimal('5500000'))
        self.assertEqual(variant.specs.count(), 2)
        self.assertTrue(variant.sku.startswith('HP-880-V'))

    def test_same_combination_reuses_existing_variant(self):
        """Bir xil tarkib ikkinchi marta yig'ilsa — yangi mahsulot yaratilmaydi."""
        first = self._configuration([(self.ssd, 1), (self.gpu, 1)])
        self.client.post(f'/api/configurations/{first.id}/finalize/')
        first.refresh_from_db()

        second = self._configuration([(self.gpu, 1), (self.ssd, 1)])  # tartibi boshqa
        self.assertEqual(second.signature, first.signature)
        self.assertEqual(second.matching_variant, first.variant)

        response = self.client.post(f'/api/configurations/{second.id}/finalize/')
        self.assertEqual(response.status_code, 200, response.data)
        second.refresh_from_db()
        self.assertEqual(second.variant, first.variant)
        self.assertEqual(Product.objects.filter(base_model=self.base).count(), 1)

    def test_ready_variant_price_is_used(self):
        first = self._configuration([(self.ssd, 1), (self.gpu, 1)])
        self.client.post(f'/api/configurations/{first.id}/finalize/')
        first.refresh_from_db()

        # Ombordagi tayyor pozitsiya narxi o'zgardi
        variant = first.variant
        variant.sale_price = Decimal('5000000')
        variant.save()

        second = self._configuration([(self.ssd, 1), (self.gpu, 1)])
        self.assertEqual(second.items_total, Decimal('5500000'))
        self.assertEqual(second.total_price, Decimal('5000000'))

    def test_different_combination_creates_second_variant(self):
        first = self._configuration([(self.ssd, 1), (self.gpu, 1)])
        self.client.post(f'/api/configurations/{first.id}/finalize/')

        second = self._configuration([(self.ssd, 2), (self.gpu, 1)])
        self.assertIsNone(second.matching_variant)
        self.client.post(f'/api/configurations/{second.id}/finalize/')
        self.assertEqual(Product.objects.filter(base_model=self.base).count(), 2)

    def test_stock_check_shows_ready_variant(self):
        configuration = self._configuration([(self.ssd, 1), (self.gpu, 1)])
        self.client.post(f'/api/configurations/{configuration.id}/finalize/')
        response = self.client.get(f'/api/configurations/{configuration.id}/stock-check/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['ready_variant'].startswith('HP-880-V'))
