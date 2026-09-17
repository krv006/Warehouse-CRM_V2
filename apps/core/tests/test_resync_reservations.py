from decimal import Decimal
from io import StringIO

from django.core.management import call_command

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
from apps.inventory.services import apply_movement


class ResyncReservationsTests(APITestCase):
    """4-to'plam §1: eski (3-to'plamgacha yozilgan) noto'g'ri bronlar tozalanadi."""

    def setUp(self):
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.base = Product.objects.create(
            sku='DELL-7010', name='Dell OptiPlex 7010', kind=Product.Kind.MACHINE,
        )
        self.cpu = Product.objects.create(
            sku='CPU-14400', name='Intel i5-14400F', kind=Product.Kind.COMPONENT,
        )
        ProductSpec.objects.create(
            product=self.base, component=self.cpu, label='CPU', quantity=1,
        )
        self.ram = Product.objects.create(
            sku='RAM-32', name='Corsair DDR5 32', kind=Product.Kind.COMPONENT,
        )
        for product, quantity in [(self.base, 12), (self.cpu, 15), (self.ram, 20)]:
            apply_movement(
                product=product, warehouse=self.warehouse,
                type=StockMovement.Type.IN, quantity=Decimal(quantity),
            )

    def _modify_config(self, status=Configuration.Status.APPROVED):
        configuration = Configuration.objects.create(
            base_product=self.base, warehouse=self.warehouse,
            created_by=self.engineer, mode=Configuration.Mode.MODIFY,
            quantity=10, status=status,
        )
        ConfigurationItem.objects.create(
            configuration=configuration, component=self.cpu, label='CPU', quantity=1,
        )
        ConfigurationItem.objects.create(
            configuration=configuration, component=self.ram, label='RAM', quantity=1,
        )
        return configuration

    def _write_legacy_reservation(self, configuration, product, quantity):
        """3-to'plamgacha bo'lgan xato bron: mashina ichidagi qism band, model emas."""
        StockReservation.objects.create(
            product=product, warehouse=self.warehouse,
            quantity=Decimal(quantity), kind=StockReservation.Kind.SOFT,
            configuration=configuration,
        )

    def test_legacy_reservations_rebuilt_by_new_definition(self):
        """Modify'da CPU broni o'chib, model + qo'shilgan RAM band bo'ladi."""
        configuration = self._modify_config()
        self._write_legacy_reservation(configuration, self.cpu, 10)  # XATO: ichidagi qism
        # Model umuman band qilinmagan edi — bu ham xatoning bir qismi

        call_command('resync_reservations', stdout=StringIO())

        active = {
            r.product_id: r.quantity
            for r in StockReservation.objects.filter(
                configuration=configuration,
                status=StockReservation.Status.ACTIVE,
            )
        }
        self.assertEqual(active, {
            self.base.pk: Decimal('10'),
            self.ram.pk: Decimal('10'),
        })  # CPU yo'q — u mashinaning ichida

    def test_terminal_configuration_released_not_rebuilt(self):
        """`sold` hujjat broni bo'shatiladi va qaytadan yozilmaydi."""
        configuration = self._modify_config(status=Configuration.Status.SOLD)
        self._write_legacy_reservation(configuration, self.cpu, 10)

        out = StringIO()
        call_command('resync_reservations', stdout=out)

        self.assertFalse(
            StockReservation.objects.filter(
                configuration=configuration,
                status=StockReservation.Status.ACTIVE,
            ).exists(),
        )
        self.assertIn("bo'shatildi", out.getvalue())
