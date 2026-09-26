from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.configurator.models import Configuration, ConfigurationItem
from apps.inventory.models import Product, ProductSpec, StockMovement, StockReservation, Warehouse
from apps.inventory.services import apply_movement, sync_contract_reservations
from apps.sales.models import Contract, ContractItem


class MatchingVariantReservationTests(APITestCase):
    """22-§6 (21-§1 regressiyasi): `build` + tarkib zavodnikiday bo'lsa,
    bron BUTLOVCHIGA emas, BAZAVIY MODELGA tushishi kerak — aks holda
    boshqa savdo shu modelni sotib yuboradi va `ship` to'lovdan keyin 400
    beradi, butlovchilar esa umuman ishlatilmagan holda band bo'lib qoladi.
    """

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.hp = Product.objects.create(
            sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE,
            sale_price=Decimal('12000000'),
        )
        self.ram = Product.objects.create(
            sku='RAM-1', name='RAM 16GB', kind=Product.Kind.COMPONENT,
            sale_price=Decimal('900000'),
        )
        ProductSpec.objects.create(product=self.hp, component=self.ram, label='RAM', quantity=1)
        apply_movement(
            product=self.ram, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('10'),
        )

    def _matching_configuration(self):
        """Tarkib zavod spetsifikatsiyasiga aynan teng — `matching_variant` ishlaydi."""
        configuration = Configuration.objects.create(
            base_product=self.hp, warehouse=self.warehouse, client=self.mijoz,
            mode=Configuration.Mode.BUILD, created_by=self.sales,
        )
        ConfigurationItem.objects.create(
            configuration=configuration, component=self.ram,
            label='RAM', quantity=1, unit_price=Decimal('900000'),
        )
        return configuration

    def _contract_for(self, configuration):
        contract = Contract.objects.create(client=self.mijoz, created_by=self.sales)
        ContractItem.objects.create(
            contract=contract, product=configuration.base_product,
            quantity=configuration.quantity, unit_price=Decimal('12000000'),
            configuration=configuration,
        )
        sync_contract_reservations(contract)
        return contract

    def test_matching_build_reserves_base_product_not_component(self):
        apply_movement(
            product=self.hp, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('2'),
        )
        configuration = self._matching_configuration()
        self.assertIsNotNone(configuration.matching_variant)
        self._contract_for(configuration)

        self.assertTrue(
            StockReservation.objects.filter(
                product=self.hp, status=StockReservation.Status.ACTIVE,
            ).exists(),
        )
        self.assertFalse(
            StockReservation.objects.filter(
                product=self.ram, status=StockReservation.Status.ACTIVE,
            ).exists(),
        )

    def test_missing_items_shows_base_product_when_out_of_stock(self):
        configuration = self._matching_configuration()
        # HP qoldig'i 0 — matching_variant baribir topiladi (tarkib mos),
        # lekin ombordagi bazaviy model yetmaydi
        missing = configuration.missing_items
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]['product'], self.hp)

    def test_build_with_changed_composition_reserves_components(self):
        """Tarkib o'zgargan (zavodnikidan farqli) — bron bugungidek butlovchilarda."""
        configuration = self._matching_configuration()
        extra = Product.objects.create(
            sku='SSD-1', name='SSD 1TB', kind=Product.Kind.COMPONENT,
            sale_price=Decimal('700000'),
        )
        apply_movement(
            product=extra, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('5'),
        )
        ConfigurationItem.objects.create(
            configuration=configuration, component=extra,
            label='SSD', quantity=1, unit_price=Decimal('700000'),
        )
        self.assertIsNone(configuration.matching_variant)
        self._contract_for(configuration)

        self.assertTrue(
            StockReservation.objects.filter(
                product=self.ram, status=StockReservation.Status.ACTIVE,
            ).exists(),
        )
        self.assertFalse(
            StockReservation.objects.filter(
                product=self.hp, status=StockReservation.Status.ACTIVE,
            ).exists(),
        )

    def test_modify_mode_reserves_base_and_added_components(self):
        """`modify` — bugungidek: bazaviy model + qo'shilgan qatorlar."""
        added = Product.objects.create(
            sku='GPU-1', name='RTX 4060', kind=Product.Kind.COMPONENT,
            sale_price=Decimal('3000000'),
        )
        apply_movement(
            product=added, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('3'),
        )
        apply_movement(
            product=self.hp, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('2'),
        )
        configuration = Configuration.objects.create(
            base_product=self.hp, warehouse=self.warehouse, client=self.mijoz,
            mode=Configuration.Mode.MODIFY, created_by=self.sales,
        )
        ConfigurationItem.objects.create(
            configuration=configuration, component=added,
            label='GPU', quantity=1, unit_price=Decimal('3000000'),
        )
        required = dict(configuration.required_from_stock)
        self.assertIn(self.hp, required)
        self.assertIn(added, required)
        self.assertNotIn(self.ram, required)

    def test_second_contract_on_same_base_product_sees_it_unavailable(self):
        """Ikkinchi savdo bandligini ko'radi — `ship`da kutilmagan 400 yo'q."""
        from apps.inventory.services import sellable_quantity

        apply_movement(
            product=self.hp, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('1'),
        )
        first_configuration = self._matching_configuration()
        self._contract_for(first_configuration)

        self.assertLessEqual(sellable_quantity(self.hp, self.warehouse), 0)
