from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.configurator.models import Configuration, ConfigurationItem
from apps.inventory.models import (
    Product,
    ProductSpec,
    StockMovement,
    StockReservation,
    Warehouse,
)
from apps.inventory.services import (
    apply_movement,
    available_quantity,
    sync_configuration_reservations,
)
from apps.procurement.models import Replenishment


class RequiredFromStockTests(APITestCase):
    """3-to'plam §1: tayyor model — yaxlit birlik.

    `modify` OMBORDAN faqat modelning o'zini va qo'shilgan qatorlarni oladi;
    mashina ichidagi o'zgarmagan qismlar band ham qilinmaydi,
    yetishmovchilikka ham tushmaydi.
    """

    def setUp(self):
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        User.objects.create_user('buy', password='p', role=User.Role.SUPPLIER)
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.base = Product.objects.create(
            sku='DELL-7010', name='Dell OptiPlex 7010 MT', kind=Product.Kind.MACHINE,
            cost_price=Decimal('8000000'), sale_price=Decimal('12000000'),
        )
        # Zavod tarkibi — mashina ichida keladigan, o'zgartirilmaydigan qism
        self.cpu = Product.objects.create(
            sku='CPU-14400', name='Intel Core i5-14400F', kind=Product.Kind.COMPONENT,
            sale_price=Decimal('2500000'),
        )
        ProductSpec.objects.create(
            product=self.base, component=self.cpu, label='CPU', quantity=1,
        )
        # Tarkibga qo'shiladigan qism
        self.ram = Product.objects.create(
            sku='RAM-32', name='Corsair DDR5 32 GB', kind=Product.Kind.COMPONENT,
            sale_price=Decimal('1500000'),
        )
        self.client.force_authenticate(self.engineer)

    def _stock_in(self, product, quantity):
        apply_movement(
            product=product, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal(quantity),
        )

    def _modify_config(self, quantity=10, status=Configuration.Status.DRAFT):
        """10 talik partiya: zavod CPU o'zgarmaydi, RAM qo'shiladi."""
        configuration = Configuration.objects.create(
            base_product=self.base, warehouse=self.warehouse,
            created_by=self.engineer, mode=Configuration.Mode.MODIFY,
            quantity=quantity, status=status,
        )
        ConfigurationItem.objects.create(
            configuration=configuration, component=self.cpu, label='CPU', quantity=1,
        )
        ConfigurationItem.objects.create(
            configuration=configuration, component=self.ram, label='RAM', quantity=1,
        )
        return configuration

    def test_modify_reserves_model_and_added_only(self):
        """Bron: model ×10 va qo'shilgan RAM ×10 — ichidagi CPU band qilinmaydi."""
        self._stock_in(self.base, 12)
        self._stock_in(self.ram, 20)
        self._stock_in(self.cpu, 15)
        configuration = self._modify_config()
        sync_configuration_reservations(configuration)

        reservations = {
            r.product_id: r.quantity
            for r in StockReservation.objects.filter(configuration=configuration)
        }
        self.assertEqual(reservations, {
            self.base.pk: Decimal('10'),  # modelning O'ZI band
            self.ram.pk: Decimal('10'),   # qo'shilgani band
        })  # CPU yo'q — u mashinaning ichida keladi

    def test_missing_includes_base_model_shortage(self):
        """Omborda 2 ta model bor, 10 kerak — missing'da model ×8."""
        self._stock_in(self.base, 2)
        self._stock_in(self.ram, 20)
        configuration = self._modify_config()

        missing = configuration.missing_items
        self.assertEqual(len(missing), 1)
        row = missing[0]
        self.assertEqual(row['product'], self.base)
        self.assertEqual(row['needed'], 10)
        self.assertEqual(row['shortage'], Decimal('8'))

    def test_unchanged_row_never_missing(self):
        """O'zgarmagan CPU omborda umuman yo'q — baribir yetishmovchilik emas."""
        self._stock_in(self.base, 10)
        self._stock_in(self.ram, 20)  # CPU: 0 dona
        configuration = self._modify_config()

        self.assertEqual(configuration.missing_items, [])

    def test_request_procurement_includes_base_model(self):
        """TLD da bazaviy model qatori bo'lsin — 8 dona, ta'minotchi narxida."""
        self._stock_in(self.base, 2)
        self._stock_in(self.ram, 20)
        configuration = self._modify_config(status=Configuration.Status.APPROVED)

        response = self.client.post(
            f'/api/configurations/{configuration.id}/request-procurement/',
        )
        self.assertEqual(response.status_code, 201, response.data)
        item = Replenishment.objects.get().items.get()
        self.assertEqual(item.product, self.base)
        self.assertEqual(item.quantity, Decimal('8'))
        self.assertEqual(item.unit_price, Decimal('8000000'))

    def test_assemble_passes_after_replenishment_received(self):
        """TLD kirim qilingach yig'ish o'tadi (avval model kelmagani uchun o'tmasdi)."""
        self._stock_in(self.base, 2)
        self._stock_in(self.ram, 20)
        configuration = self._modify_config(status=Configuration.Status.APPROVED)
        self.client.post(
            f'/api/configurations/{configuration.id}/request-procurement/',
        )
        replenishment = Replenishment.objects.get()
        replenishment.status = Replenishment.Status.ORDERED
        replenishment.save()
        self.client.force_authenticate(self.bugalter)
        response = self.client.post(f'/api/replenishments/{replenishment.id}/receive/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(available_quantity(self.base, self.warehouse), Decimal('10'))

        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configurations/{configuration.id}/assemble/')
        self.assertEqual(response.status_code, 200, response.data)
        configuration.refresh_from_db()
        # 10 ta model va 10 ta RAM ishga ketdi, 10 ta variant yig'ildi
        self.assertEqual(available_quantity(self.base, self.warehouse), Decimal('0'))
        self.assertEqual(available_quantity(self.ram, self.warehouse), Decimal('10'))
        self.assertEqual(
            available_quantity(configuration.variant, self.warehouse), Decimal('10'),
        )

    def test_assemble_blocked_lists_model_shortage(self):
        """Model yetmasa yig'ish 400 — xabarda modelning o'zi turadi."""
        self._stock_in(self.base, 2)
        self._stock_in(self.ram, 20)
        configuration = self._modify_config(status=Configuration.Status.APPROVED)

        response = self.client.post(f'/api/configurations/{configuration.id}/assemble/')
        self.assertEqual(response.status_code, 400)
        self.assertIn('Dell OptiPlex 7010 MT', str(response.data['items']))

    def test_build_mode_unchanged(self):
        """Build rejimida xulq eskicha: har bir qator × partiya."""
        self._stock_in(self.ram, 4)
        configuration = Configuration.objects.create(
            base_product=self.base, warehouse=self.warehouse,
            created_by=self.engineer, quantity=3,
        )
        ConfigurationItem.objects.create(
            configuration=configuration, component=self.ram, label='RAM', quantity=2,
        )
        self.assertEqual(
            configuration.required_from_stock, [(self.ram, 6)],
        )
        missing = configuration.missing_items
        self.assertEqual(missing[0]['product'], self.ram)
        self.assertEqual(missing[0]['shortage'], Decimal('2'))

        sync_configuration_reservations(configuration)
        reservation = StockReservation.objects.get(configuration=configuration)
        self.assertEqual(reservation.product, self.ram)
        self.assertEqual(reservation.quantity, Decimal('4'))  # boricha rejalanadi
