from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.inventory.models import Product
from apps.procurement.models import Replenishment, ReplenishmentItem


class ReceiveCostPriceTests(APITestCase):
    """Kirimdan keyin xarid narxi katalogga tushadi (bug-report: TLD-00031).

    Avval receive() faqat qoldiqni oshirardi — mahsulot cost_price=0 bo'lib
    qolib, configurator qatori needs_price bilan finalize'ni 400 qilardi.
    """

    def setUp(self):
        from apps.inventory.services import main_warehouse

        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.warehouse = main_warehouse()
        # Buyurtma orqali kirgan yangi mahsulot — narxi hali yo'q
        self.cooler = Product.objects.create(
            sku='MAH-00042', name='Cooler 32/62', kind=Product.Kind.COMPONENT,
        )
        self.client.force_authenticate(self.bugalter)

    def _make_ordered(self, unit_price, configuration=None):
        replenishment = Replenishment.objects.create(
            warehouse=self.warehouse, status=Replenishment.Status.ORDERED,
            configuration=configuration, created_by=self.bugalter,
        )
        ReplenishmentItem.objects.create(
            replenishment=replenishment, product=self.cooler,
            quantity=1, unit_price=Decimal(unit_price),
        )
        return replenishment

    def _receive(self, replenishment):
        return self.client.post(f'/api/replenishments/{replenishment.id}/receive/')

    def test_receive_updates_cost_price(self):
        replenishment = self._make_ordered('1000000')
        response = self._receive(replenishment)
        self.assertEqual(response.status_code, 200, response.data)

        self.cooler.refresh_from_db()
        self.assertEqual(self.cooler.cost_price, Decimal('1000000'))
        self.assertEqual(self.cooler.stock_price, Decimal('1000000'))

    def test_zero_price_does_not_wipe_existing_cost(self):
        """Narxsiz qator mavjud tannarxni 0 ga tushirmaydi."""
        self.cooler.cost_price = Decimal('900000')
        self.cooler.save()
        replenishment = self._make_ordered('0')
        self._receive(replenishment)

        self.cooler.refresh_from_db()
        self.assertEqual(self.cooler.cost_price, Decimal('900000'))

    def test_linked_configuration_row_unlocks(self):
        """Bug-report stsenariysi: kirimdan keyin konfiguratsiya qatori narx oladi.

        needs_price False bo'ladi — sales endi finalize qila oladi.
        """
        from apps.configurator.models import Configuration, ConfigurationItem

        base = Product.objects.create(sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE)
        configuration = Configuration.objects.create(
            base_product=base, warehouse=self.warehouse,
        )
        config_item = ConfigurationItem.objects.create(
            configuration=configuration, component=self.cooler,
            label='COOLER', quantity=1,
        )
        self.assertTrue(config_item.needs_price)

        replenishment = self._make_ordered('1000000', configuration=configuration)
        self._receive(replenishment)

        config_item.refresh_from_db()
        self.assertEqual(config_item.unit_price, Decimal('1000000'))
        self.assertFalse(config_item.needs_price)
        self.assertEqual(config_item.available, Decimal('1'))
