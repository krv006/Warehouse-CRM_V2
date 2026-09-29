from datetime import date
from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.configurator.models import Act, Configuration, ConfigurationItem
from apps.inventory.models import Product, ProductSpec, StockMovement, Warehouse
from apps.inventory.services import apply_movement
from apps.procurement.models import Replenishment
from apps.sales.models import Contract


class OrderModeDefaultSelectionTests(APITestCase):
    """25-§6: `take`da rejim avtomatik tanlanadi.

    Tarkibi bor -> build (bugungidek); tarkibi yo'q-u omborda bor -> modify;
    ikkalasi ham yo'q (yangi model) -> order (25-§3: shu bilan `modify`
    erta bloklanishi keraksiz bo'lib qoladi — endi to'g'ri rejim taklif
    qilinadi, noto'g'risi umuman so'ralmaydi).
    """

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )

    def _zvk(self):
        self.client.force_authenticate(self.sales)
        return self.client.post('/api/configuration-requests/', {
            'text': 'yangi model', 'client': self.mijoz.id, 'quantity': 1,
        }, format='json').data['id']

    def _take(self, **take_body):
        request_id = self._zvk()
        self.client.force_authenticate(self.engineer)
        return self.client.post(
            f'/api/configuration-requests/{request_id}/take/', take_body, format='json',
        )

    def test_new_model_without_spec_or_stock_defaults_to_order(self):
        response = self._take(new_base_product_name='Dell Precision 3680')
        self.assertEqual(response.status_code, 200, response.data)
        configuration = Configuration.objects.get(pk=response.data['configuration'])
        self.assertEqual(configuration.mode, Configuration.Mode.ORDER)

    def test_model_with_spec_still_defaults_to_build(self):
        base = Product.objects.create(sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE)
        ram = Product.objects.create(sku='RAM-16', name='RAM 16', kind=Product.Kind.COMPONENT)
        ProductSpec.objects.create(product=base, component=ram, label='RAM', quantity=1)
        response = self._take(base_product=base.id)
        self.assertEqual(response.status_code, 200, response.data)
        configuration = Configuration.objects.get(pk=response.data['configuration'])
        self.assertEqual(configuration.mode, Configuration.Mode.BUILD)

    def test_model_without_spec_but_in_stock_defaults_to_modify(self):
        base = Product.objects.create(sku='HP-990', name='HP 990', kind=Product.Kind.MACHINE)
        warehouse = Warehouse.objects.create(name='Asosiy ombor')
        apply_movement(
            product=base, warehouse=warehouse, type=StockMovement.Type.IN, quantity=Decimal('2'),
        )
        response = self._take(base_product=base.id)
        self.assertEqual(response.status_code, 200, response.data)
        configuration = Configuration.objects.get(pk=response.data['configuration'])
        self.assertEqual(configuration.mode, Configuration.Mode.MODIFY)

    def test_explicit_order_mode_allowed_even_with_spec(self):
        """§7 case: `order` + tarkibi bor model — ruxsat, 'shu tarkib bilan
        tayyor holda olib kelinsin' ham haqiqiy holat."""
        base = Product.objects.create(sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE)
        ram = Product.objects.create(sku='RAM-16', name='RAM 16', kind=Product.Kind.COMPONENT)
        ProductSpec.objects.create(product=base, component=ram, label='RAM', quantity=1)
        response = self._take(base_product=base.id, mode='order')
        self.assertEqual(response.status_code, 200, response.data)
        configuration = Configuration.objects.get(pk=response.data['configuration'])
        self.assertEqual(configuration.mode, Configuration.Mode.ORDER)

    def test_explicit_modify_on_new_model_still_blocked_with_updated_message(self):
        """25-§3: guard o'zi ishlayveradi (aniq `modify` so'ralsa), faqat
        xabar `order`ni taklif qiladi."""
        response = self._take(new_base_product_name='Dell Precision 3680', mode='modify')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("omborda ham yo'q", str(response.data))
        self.assertIn('order', str(response.data))
        self.assertEqual(Configuration.objects.count(), 0)


class OrderModeFlowTests(APITestCase):
    """25-§6/§9: yangi model butun holda buyurtma qilinadi."""

    def setUp(self):
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.buyurtmachi = User.objects.create_user('buy', password='p', role=User.Role.SUPPLIER)
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.base = Product.objects.create(
            sku='DELL-3680', name='Dell Precision 3680', kind=Product.Kind.MACHINE,
        )
        self.ram = Product.objects.create(sku='RAM-32', name='RAM 32 GB', kind=Product.Kind.COMPONENT)
        self.ssd = Product.objects.create(sku='SSD-1TB', name='SSD 1 TB', kind=Product.Kind.COMPONENT)
        self.configuration = Configuration.objects.create(
            base_product=self.base, warehouse=self.warehouse, created_by=self.engineer,
            mode=Configuration.Mode.ORDER, status=Configuration.Status.APPROVED,
        )
        ConfigurationItem.objects.create(
            configuration=self.configuration, component=self.ram, label='RAM', quantity=1,
        )
        ConfigurationItem.objects.create(
            configuration=self.configuration, component=self.ssd, label='SSD', quantity=1,
        )
        mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.contract = Contract.objects.create(
            client=mijoz, configuration=self.configuration,
            status=Contract.Status.ACTIVE, total_amount=Decimal('20000000'),
            created_by=self.sales,
        )
        self.act = Act.objects.create(
            number='ACT-001', title='Dell Precision 3680',
            issued_at=date.today(), created_by=self.engineer,
        )

    def test_required_from_stock_is_only_the_model(self):
        self.assertEqual(
            self.configuration.required_from_stock, [(self.base, 1)],
        )

    def test_missing_items_shows_only_the_model(self):
        missing = self.configuration.missing_items
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]['product'], self.base)
        self.assertEqual(missing[0]['needed'], 1)

    def test_no_price_required_on_spec_rows(self):
        """Qatorlarga narx kerak emas — spetsifikatsiya, buyurtma ro'yxati emas."""
        self.assertEqual(self.configuration.items_without_price, [])

    def test_request_procurement_creates_single_line_with_specification_note(self):
        self.client.force_authenticate(self.engineer)
        response = self.client.post(
            f'/api/configurations/{self.configuration.id}/request-procurement/',
        )
        self.assertEqual(response.status_code, 201, response.data)

        replenishment = Replenishment.objects.get()
        items = list(replenishment.items.all())
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].product, self.base)
        self.assertEqual(items[0].quantity, Decimal('1'))
        self.assertIn('BUTUN MODEL', items[0].note)
        self.assertIn('RAM x1', items[0].note)
        self.assertIn('SSD x1', items[0].note)

    def test_finalize_passes_without_assemble(self):
        self.client.force_authenticate(self.engineer)
        response = self.client.post(
            f'/api/configurations/{self.configuration.id}/finalize/',
            {'act': self.act.id}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.configuration.refresh_from_db()
        self.assertIsNone(self.configuration.assembled_at)
        self.assertIn(self.configuration.status, (Configuration.Status.READY, Configuration.Status.SOLD))

    def test_finalize_copies_items_to_product_specs(self):
        """Kirim bo'ldi (bu yerda to'g'ridan finalize orqali simulyatsiya
        qilinadi) — `Product.specs` tarkib bilan to'ladi."""
        self.client.force_authenticate(self.engineer)
        response = self.client.post(
            f'/api/configurations/{self.configuration.id}/finalize/',
            {'act': self.act.id}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)

        specs = {
            spec.component_id: spec.quantity for spec in self.base.specs.all()
        }
        self.assertEqual(specs, {self.ram.id: 1, self.ssd.id: 1})

    def test_second_request_for_same_model_loads_spec_and_opens_build(self):
        """Ikkinchi zayavka, o'sha model: `copy_factory_spec` tarkibni
        yuklaydi, `build`/`modify` ochiladi (endi `order` shart emas)."""
        self.client.force_authenticate(self.engineer)
        finalize_response = self.client.post(
            f'/api/configurations/{self.configuration.id}/finalize/',
            {'act': self.act.id}, format='json',
        )
        self.assertEqual(finalize_response.status_code, 200, finalize_response.data)

        mijoz2 = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Vali Aliyev',
            passport='AA1112224', jshshir='11112222444455', phone='+998900000002',
        )
        self.client.force_authenticate(self.sales)
        request_id = self.client.post('/api/configuration-requests/', {
            'text': 'yana bitta Dell', 'client': mijoz2.id, 'quantity': 1,
            'base_product': self.base.id,
        }, format='json').data['id']
        self.client.force_authenticate(self.engineer)
        take_response = self.client.post(
            f'/api/configuration-requests/{request_id}/take/',
        )
        self.assertEqual(take_response.status_code, 200, take_response.data)
        second_configuration = Configuration.objects.get(pk=take_response.data['configuration'])
        self.assertEqual(second_configuration.mode, Configuration.Mode.BUILD)
        components = set(second_configuration.items.values_list('component_id', flat=True))
        self.assertEqual(components, {self.ram.id, self.ssd.id})


class OrderModeRegressionTests(APITestCase):
    """25-§6 §7: eski `build`/`modify` zanjirlar o'zgarmaydi."""

    def setUp(self):
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')

    def test_build_mode_required_from_stock_unaffected(self):
        base = Product.objects.create(sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE)
        ram = Product.objects.create(sku='RAM-16', name='RAM 16', kind=Product.Kind.COMPONENT)
        configuration = Configuration.objects.create(
            base_product=base, warehouse=self.warehouse, created_by=self.engineer,
            mode=Configuration.Mode.BUILD,
        )
        ConfigurationItem.objects.create(
            configuration=configuration, component=ram, label='RAM', quantity=2,
        )
        self.assertEqual(configuration.required_from_stock, [(ram, 2)])
        self.assertEqual(configuration.items_without_price, list(configuration.items.all()))

    def test_modify_mode_finalize_still_requires_assemble(self):
        base = Product.objects.create(sku='HP-990', name='HP 990', kind=Product.Kind.MACHINE)
        apply_movement(
            product=base, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('1'),
        )
        configuration = Configuration.objects.create(
            base_product=base, warehouse=self.warehouse, created_by=self.engineer,
            mode=Configuration.Mode.MODIFY, status=Configuration.Status.APPROVED,
        )
        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configurations/{configuration.id}/finalize/')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('yig\'ilsin', str(response.data))
