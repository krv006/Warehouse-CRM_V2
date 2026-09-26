from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.configurator.models import Configuration, ConfigurationItem, ConfigurationRequest
from apps.inventory.models import Product, StockMovement, Warehouse
from apps.inventory.services import apply_movement
from apps.sales.models import Contract, ContractItem


class TakeRejectsVariantAsBaseModelTests(APITestCase):
    """22-§7.2 (21-§7 jadvalidan yozilmagan test #1): `take`da variant
    bazaviy model qilib berilsa — 400 (kod allaqachon bor, himoyasiz edi)."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.base = Product.objects.create(
            sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE,
        )
        self.variant = Product.objects.create(
            sku='HP-880-V01', name='HP 880 (variant)', kind=Product.Kind.MACHINE,
            base_model=self.base,
        )

    def test_take_with_variant_base_product_is_400(self):
        self.client.force_authenticate(self.sales)
        request_id = self.client.post('/api/configuration-requests/', {
            'text': 'x', 'client': self.mijoz.id,
        }, format='json').data['id']

        self.client.force_authenticate(self.engineer)
        response = self.client.post(
            f'/api/configuration-requests/{request_id}/take/',
            {'base_product': self.variant.id}, format='json',
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(Configuration.objects.exists())


class CatalogHidesVariantsTests(APITestCase):
    """22-§7.2 (test #2): variant sukut bo'yicha katalogda yo'q,
    `?include_variants=true` bilan ko'rinadi."""

    def setUp(self):
        self.admin = User.objects.create_user('adm', password='p', role=User.Role.ADMIN)
        self.base = Product.objects.create(
            sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE,
        )
        self.variant = Product.objects.create(
            sku='HP-880-V01', name='HP 880 (variant)', kind=Product.Kind.MACHINE,
            base_model=self.base,
        )

    def test_variant_hidden_by_default(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get('/api/products/')
        ids = {row['id'] for row in response.data['results']}
        self.assertIn(self.base.id, ids)
        self.assertNotIn(self.variant.id, ids)

    def test_variant_visible_with_include_variants(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get('/api/products/?include_variants=true')
        ids = {row['id'] for row in response.data['results']}
        self.assertIn(self.variant.id, ids)


class ProcurementListsExcludeVariantsTests(APITestCase):
    """22-§7.2 (test #3): TLD/yetishmayotganlar ro'yxatida `base_model`
    li qator (variant) yo'q."""

    def setUp(self):
        self.supplier = User.objects.create_user('buy', password='p', role=User.Role.SUPPLIER)
        self.base = Product.objects.create(
            sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE, reorder_level=5,
        )
        self.variant = Product.objects.create(
            sku='HP-880-V01', name='HP 880 (variant)', kind=Product.Kind.MACHINE,
            base_model=self.base, reorder_level=5,
        )

    def test_low_stock_excludes_variant(self):
        self.client.force_authenticate(self.supplier)
        response = self.client.get('/api/replenishments/low-stock/')
        self.assertEqual(response.status_code, 200, response.data)
        ids = {row['id'] for row in response.data}
        self.assertIn(self.base.id, ids)
        self.assertNotIn(self.variant.id, ids)

    def test_needs_price_excludes_variant(self):
        self.admin = User.objects.create_user('adm', password='p', role=User.Role.ADMIN)
        Product.objects.filter(pk=self.base.pk).update(sale_price=0, cost_price=0)
        Product.objects.filter(pk=self.variant.pk).update(sale_price=0, cost_price=0)
        self.client.force_authenticate(self.admin)
        response = self.client.get('/api/products/?needs_price=true&include_variants=true')
        ids = {row['id'] for row in response.data['results']}
        self.assertNotIn(self.variant.id, ids)


class ShipSkipsMovementForMatchingVariantTests(APITestCase):
    """22-§7.2 (test #4): `ship`da konfiguratsiyali qator bo'yicha — agar
    yig'ishda haqiqatan narsa iste'mol qilingan bo'lsa (tarkib zavod
    standartidan farqli, `variant` bo'sh qoladi), mol allaqachon chiqqan —
    `ship` ikkinchi marta bazaviy modelni ombordan CHIQARMASLIGI kerak
    (u hech qachon omborda bo'lmagan ham)."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.admin = User.objects.create_user('adm', password='p', role=User.Role.ADMIN)
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
        from apps.inventory.models import ProductSpec

        ProductSpec.objects.create(product=self.hp, component=self.ram, label='RAM', quantity=1)
        apply_movement(
            product=self.ram, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('5'),
        )
        # 21-§1.3: tarkibni zavod spetsifikatsiyasidan ataylab farqlantiramiz
        # — aks holda matching_variant topilib, yig'ish shart emas deb
        # topiladi (bu testning maqsadi aksincha — HAQIQIY iste'molni sinash)
        self.ssd = Product.objects.create(
            sku='SSD-1', name='SSD 1TB', kind=Product.Kind.COMPONENT,
            sale_price=Decimal('700000'),
        )
        apply_movement(
            product=self.ssd, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('5'),
        )

    def _pay(self, contract):
        from apps.sales.services import approve_contract, confirm_didox, confirm_payment, send_didox

        self.client.force_authenticate(self.sales)
        self.client.patch(
            f'/api/contracts/{contract.id}/document/', {'body': '<p>Matn</p>'}, format='json',
        )
        response = self.client.post(f'/api/contracts/{contract.id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)
        contract.refresh_from_db()
        approve_contract(contract, self.admin)
        contract.refresh_from_db()
        if contract.status == Contract.Status.PENDING_ADMIN:
            approve_contract(contract, self.admin)
            contract.refresh_from_db()
        send_didox(contract, self.admin, 'DDX-1')
        confirm_didox(contract, self.admin)
        contract.refresh_from_db()
        confirm_payment(contract, self.admin, amount=contract.total_amount)
        contract.refresh_from_db()

    def test_ship_creates_no_movement_for_consumed_assembly(self):
        from datetime import date

        from apps.configurator.models import Act, ConfigurationItem

        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/configuration-requests/', {
            'text': '1 ta HP 880', 'base_product': self.hp.id,
            'client': self.mijoz.id, 'quantity': 1,
        }, format='json')
        request_obj = ConfigurationRequest.objects.get(pk=response.data['id'])

        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configuration-requests/{request_obj.id}/take/')
        request_obj.refresh_from_db()
        configuration = request_obj.configuration
        ConfigurationItem.objects.create(
            configuration=configuration, component=self.ssd,
            label='SSD', quantity=1, unit_price=Decimal('700000'),
        )
        self.assertIsNone(configuration.matching_variant)

        response = self.client.post(f'/api/configurations/{configuration.id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)
        self.client.force_authenticate(self.sales)
        response = self.client.post(f'/api/configurations/{configuration.id}/approve/')
        self.assertEqual(response.status_code, 200, response.data)
        contract = Contract.objects.get()
        self._pay(contract)

        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configurations/{configuration.id}/assemble/')
        self.assertEqual(response.status_code, 200, response.data)
        # Yig'ishda butlovchilar allaqachon ombordan chiqdi (haqiqiy iste'mol)
        self.assertTrue(StockMovement.objects.filter(product=self.ram, type=StockMovement.Type.OUT).exists())
        self.assertTrue(StockMovement.objects.filter(product=self.ssd, type=StockMovement.Type.OUT).exists())

        act = Act.objects.create(number='ACT-1', title='ACT', issued_at=date.today())
        response = self.client.post(
            f'/api/configurations/{configuration.id}/finalize/', {'act': act.id}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.client.force_authenticate(self.admin)
        response = self.client.post(f'/api/acts/{act.id}/approve/')
        self.assertEqual(response.status_code, 200, response.data)

        hp_movements_before = StockMovement.objects.filter(product=self.hp).count()
        self.client.force_authenticate(self.sales)
        response = self.client.post(f'/api/contracts/{contract.id}/ship/')
        self.assertEqual(response.status_code, 200, response.data)
        # 21-§1.3/22-§7.2: bazaviy model hech qachon omborda bo'lmagan —
        # `ship` uni IKKINCHI marta (yoki birinchi marta ham) chiqarmaydi
        hp_movements_after = StockMovement.objects.filter(product=self.hp).count()
        self.assertEqual(hp_movements_before, hp_movements_after)
