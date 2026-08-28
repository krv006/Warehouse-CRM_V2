from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.configurator.models import Configuration, ConfigurationItem
from apps.core.models import Notification
from apps.inventory.models import Product, StockMovement, Warehouse
from apps.inventory.services import apply_movement
from apps.procurement.models import Replenishment


class EngineerAddsAnyProductTests(APITestCase):
    """Engineer configuratordan bazada yo'q tovarni ham qo'sha oladi."""

    def setUp(self):
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.base = Product.objects.create(
            sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE,
        )
        self.configuration = Configuration.objects.create(
            base_product=self.base, warehouse=self.warehouse, created_by=self.engineer,
        )
        self.client.force_authenticate(self.engineer)

    def test_new_product_via_configuration_item(self):
        response = self.client.post('/api/configuration-items/', {
            'configuration': self.configuration.id,
            'new_component_name': 'RAM 32 GB',
            'label': 'RAM',
            'quantity': 2,
            'unit_price': '900000',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        product = Product.objects.get(name='RAM 32 GB')
        self.assertEqual(product.kind, Product.Kind.COMPONENT)
        self.assertEqual(product.cost_price, Decimal('900000'))
        self.assertEqual(response.data['component'], product.id)
        self.assertEqual(response.data['component_name'], 'RAM 32 GB')

    def test_new_product_via_nested_items(self):
        response = self.client.post('/api/configurations/', {
            'base_product': self.base.id,
            'items': [
                {'new_component_name': 'Suv sovutish bloki', 'label': 'COOLER',
                 'quantity': 1, 'unit_price': '1200000'},
            ],
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(Product.objects.filter(name='Suv sovutish bloki').exists())

    def test_existing_name_reused_not_duplicated(self):
        existing = Product.objects.create(sku='SSD-1TB', name='SSD 1 TB')
        response = self.client.post('/api/configuration-items/', {
            'configuration': self.configuration.id,
            'new_component_name': 'SSD 1 TB',
            'label': 'SSD', 'quantity': 1,
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['component'], existing.id)
        self.assertEqual(Product.objects.filter(name='SSD 1 TB').count(), 1)

    def test_item_requires_component_or_name(self):
        response = self.client.post('/api/configuration-items/', {
            'configuration': self.configuration.id, 'label': 'X', 'quantity': 1,
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('component', response.data)


class MissingToProcurementTests(APITestCase):
    """Omborda yo'q butlovchilar buyurtmachiga yuboriladi (TZ 7 zanjiri boshlanadi)."""

    def setUp(self):
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.buyurtmachi = User.objects.create_user(
            'buy', password='p', role=User.Role.SUPPLIER,
        )
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.base = Product.objects.create(
            sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE,
        )
        self.ssd = Product.objects.create(
            sku='SSD-1TB', name='SSD 1 TB', kind=Product.Kind.COMPONENT,
            cost_price=Decimal('1200000'),
        )
        self.gpu = Product.objects.create(
            sku='GPU-32', name='GPU 32', kind=Product.Kind.COMPONENT,
            cost_price=Decimal('4000000'),
        )
        apply_movement(  # SSD omborda yetarli, GPU umuman yo'q
            product=self.ssd, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('5'),
        )
        self.configuration = Configuration.objects.create(
            base_product=self.base, warehouse=self.warehouse, created_by=self.engineer,
        )
        ConfigurationItem.objects.create(
            configuration=self.configuration, component=self.ssd,
            label='SSD', quantity=1,
        )
        ConfigurationItem.objects.create(
            configuration=self.configuration, component=self.gpu,
            label='GPU', quantity=3,
        )
        self.client.force_authenticate(self.engineer)

    def _send(self):
        return self.client.post(
            f'/api/configurations/{self.configuration.id}/request-procurement/',
        )

    def test_creates_replenishment_with_missing_items(self):
        response = self._send()
        self.assertEqual(response.status_code, 201, response.data)

        replenishment = Replenishment.objects.get()
        self.assertEqual(replenishment.status, Replenishment.Status.DRAFT)
        self.assertEqual(replenishment.configuration, self.configuration)
        self.assertEqual(replenishment.warehouse, self.warehouse)

        # Faqat yetishmagani: GPU 3 dona (SSD omborda bor)
        items = list(replenishment.items.all())
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].product, self.gpu)
        self.assertEqual(items[0].quantity, Decimal('3'))
        self.assertEqual(items[0].unit_price, Decimal('4000000'))
        self.assertEqual(response.data['configuration'], self.configuration.id)

    def test_notifies_supplier_sales_and_bugalter(self):
        self._send()
        for user in (self.buyurtmachi, self.sales, self.bugalter):
            note = Notification.objects.get(user=user)
            self.assertIn(self.configuration.number, note.title)
            self.assertIn('GPU 32', note.message)
        # Engineerning o'ziga xabar shart emas
        self.assertFalse(Notification.objects.filter(user=self.engineer).exists())

    def test_400_when_everything_in_stock(self):
        apply_movement(
            product=self.gpu, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('10'),
        )
        response = self._send()
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Replenishment.objects.exists())

    def test_sales_cannot_send(self):
        self.client.force_authenticate(self.sales)
        self.assertEqual(self._send().status_code, 403)

    def test_chain_continues_to_supplier_flow(self):
        """Yaratilgan hisob TZ 7 zanjiriga tushadi: buyurtmachi submit qila oladi."""
        self._send()
        replenishment = Replenishment.objects.get()
        self.client.force_authenticate(self.buyurtmachi)
        response = self.client.post(f'/api/replenishments/{replenishment.id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], Replenishment.Status.PENDING_BUGALTER)
