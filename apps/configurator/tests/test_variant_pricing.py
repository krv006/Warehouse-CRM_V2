from datetime import date
from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.configurator.models import Act, Configuration, ConfigurationItem
from apps.inventory.models import Product


def walk_to_approved(client, config_id):
    """#4 oqimi: engineer submit -> sales approve (testlarda admin bilan).

    YANGI OQIM: approve'da SHT ochiladi, yig'ish esa to'lovdan keyin (B4) —
    testda to'lov o'rniga shartnoma to'g'ridan-to'g'ri faollashtiriladi.
    """
    from apps.sales.models import Contract

    client.post(f'/api/configurations/{config_id}/submit/')
    client.post(f'/api/configurations/{config_id}/approve/')
    Contract.objects.filter(configuration_id=config_id).update(
        status=Contract.Status.ACTIVE,
    )


def full_finalize(client, config_id, body=None, removals=None):
    """#4 to'liq zanjir: submit -> approve -> assemble -> finalize."""
    walk_to_approved(client, config_id)
    client.post(
        f'/api/configurations/{config_id}/assemble/',
        {'removals': removals} if removals else {}, format='json',
    )
    return client.post(
        f'/api/configurations/{config_id}/finalize/', body or {}, format='json',
    )


class VariantPricingTests(APITestCase):
    """TZ 6.2: narx ombordan olinadi, tayyor variant tanib olinadi."""

    def setUp(self):
        self.admin = User.objects.create_user('admin', password='p', role=User.Role.ADMIN)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.base = Product.objects.create(
            sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE,
        )
        self.ssd = Product.objects.create(
            sku='SSD-1TB', name='SSD 1 TB',
            kind=Product.Kind.COMPONENT, sale_price=Decimal('1500000'),
        )
        self.gpu = Product.objects.create(
            sku='GPU-32', name='GPU 32',
            kind=Product.Kind.COMPONENT, cost_price=Decimal('4000000'),
        )
        self.no_price = Product.objects.create(
            sku='RAM-4', name='RAM 4', kind=Product.Kind.COMPONENT,
        )
        self.act = Act.objects.create(number='ACT-001', title='ACT', issued_at=date.today())
        # YANGI OQIM B10: tasdiq (approve) mijozsiz o'tmaydi — shartnoma ochiladi
        from apps.clients.models import Client

        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        # Yig'ish (assemble) uchun butlovchilar omborda bo'lsin
        from apps.inventory.models import StockMovement, Warehouse
        from apps.inventory.services import apply_movement

        warehouse = Warehouse.objects.create(name='Asosiy ombor')
        for product in (self.ssd, self.gpu, self.no_price):
            apply_movement(
                product=product, warehouse=warehouse,
                type=StockMovement.Type.IN, quantity=Decimal('10'),
            )
        # Admin bilan: butun zanjir (submit/approve/assemble/finalize) bitta
        # testda ketadi — rol chegaralari alohida testlarda
        self.client.force_authenticate(self.admin)

    def _configuration(self, components, act=True):
        configuration = Configuration.objects.create(
            base_product=self.base, created_by=self.engineer,
            act=self.act if act else None, client=self.mijoz,
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

    def test_submit_blocked_without_price(self):
        """YANGI OQIM B2: narx tekshiruvi endi submit'da — shartnoma undan keyin."""
        configuration = self._configuration([(self.ssd, 1), (self.no_price, 1)])
        response = self.client.post(f'/api/configurations/{configuration.id}/submit/')
        self.assertEqual(response.status_code, 400)
        self.assertIn('RAM 4', str(response.data['items']))

    def test_finalize_does_not_create_variant(self):
        """21-§1.3: yig'ilgan mashina uchun alohida katalog yozuvi yaratilmaydi."""
        product_count = Product.objects.count()
        configuration = self._configuration([(self.ssd, 1), (self.gpu, 1)])
        response = full_finalize(self.client, configuration.id)
        self.assertEqual(response.status_code, 200, response.data)

        configuration.refresh_from_db()
        self.assertIsNone(configuration.variant)
        self.assertEqual(Product.objects.count(), product_count)
        contract = configuration.active_contract
        self.assertEqual(contract.items.get().product, self.base)

    def test_same_combination_creates_independent_configurations(self):
        """Bir xil tarkib ikkinchi marta yig'ilsa — mustaqil, umumiy Product yo'q."""
        first = self._configuration([(self.ssd, 1), (self.gpu, 1)])
        full_finalize(self.client, first.id)
        first.refresh_from_db()

        second = self._configuration([(self.gpu, 1), (self.ssd, 1)])  # tartibi boshqa
        self.assertEqual(second.signature, first.signature)

        response = full_finalize(self.client, second.id)
        self.assertEqual(response.status_code, 200, response.data)
        second.refresh_from_db()
        self.assertIsNone(second.variant)
        self.assertIsNone(first.variant)
        self.assertNotEqual(second.active_contract.id, first.active_contract.id)

    def test_total_price_is_items_total(self):
        """21-§1.3: narx doim qatorlar yig'indisi — variant narxiga bog'liq emas."""
        configuration = self._configuration([(self.ssd, 1), (self.gpu, 1)])
        self.assertEqual(configuration.items_total, Decimal('5500000'))
        self.assertEqual(configuration.total_price, Decimal('5500000'))

    def test_different_combination_does_not_create_variant(self):
        first = self._configuration([(self.ssd, 1), (self.gpu, 1)])
        full_finalize(self.client, first.id)

        product_count = Product.objects.count()
        second = self._configuration([(self.ssd, 2), (self.gpu, 1)])
        self.assertIsNone(second.matching_variant)
        response = full_finalize(self.client, second.id)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Product.objects.count(), product_count)

    def test_stock_check_after_finalize_has_no_ready_variant(self):
        """Tarkib zavod standartidan farq qilgani uchun tayyor pozitsiya yo'q."""
        configuration = self._configuration([(self.ssd, 1), (self.gpu, 1)])
        full_finalize(self.client, configuration.id)
        response = self.client.get(f'/api/configurations/{configuration.id}/stock-check/')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data['ready_variant'])


class BaseModelAsReadyPositionTests(APITestCase):
    """TZ 6.1-6.2: bazaviy modelning o'zi ombordagi tayyor pozitsiya."""

    def setUp(self):
        self.admin = User.objects.create_user('admin', password='p', role=User.Role.ADMIN)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.base = Product.objects.create(
            sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE,
            sale_price=Decimal('25000000'),
        )
        self.ssd = Product.objects.create(
            sku='SSD-1TB', name='SSD 1 TB', kind=Product.Kind.COMPONENT,
            sale_price=Decimal('1500000'),
        )
        self.gpu = Product.objects.create(
            sku='GPU-32', name='GPU 32', kind=Product.Kind.COMPONENT,
            sale_price=Decimal('4500000'),
        )
        from apps.inventory.models import ProductSpec, StockMovement, Warehouse
        from apps.inventory.services import apply_movement

        for component, label in [(self.ssd, 'SSD'), (self.gpu, 'GPU')]:
            ProductSpec.objects.create(
                product=self.base, component=component, label=label, quantity=1,
            )
        warehouse = Warehouse.objects.create(name='Asosiy ombor')
        apply_movement(
            product=self.base, warehouse=warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('3'),
        )
        from apps.clients.models import Client

        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        # Admin bilan: konfiguratsiya tahriri ham (engineer ishi), finalize ham
        # (sales bosqichi) bitta testda ketadi — rol chegaralari alohida testlarda
        self.client.force_authenticate(self.admin)

    def test_items_autofilled_from_factory_specs(self):
        """Model tanlanganda tarkibi avtomatik yuklanadi — qo'lda kiritish shart emas."""
        response = self.client.post('/api/configurations/', {
            'base_product': self.base.id,
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        labels = {item['label'] for item in response.data['items']}
        self.assertEqual(labels, {'SSD', 'GPU'})
        # narxlar ham ombordan olingan
        prices = {item['label']: item['unit_price'] for item in response.data['items']}
        self.assertEqual(prices['SSD'], '1500000.00')

    def test_unchanged_composition_recognized_as_base_product(self):
        """Tarkib o'zgartirilmagan — tayyor HP 880 ning o'zi va narxi qo'llanadi."""
        response = self.client.post('/api/configurations/', {
            'base_product': self.base.id,
        }, format='json')
        ready = response.data['ready_variant']
        self.assertIsNotNone(ready)
        self.assertEqual(ready['sku'], 'HP-880')
        self.assertTrue(ready['is_base_model'])
        self.assertEqual(Decimal(ready['price']), Decimal('25000000'))
        self.assertEqual(Decimal(ready['stock']), Decimal('3'))
        # 21-§1.3: umumiy narx endi doim qatorlar yig'indisi (SSD+GPU=6 mln)
        self.assertEqual(Decimal(response.data['total_price']), Decimal('6000000'))

    def test_finalize_unchanged_does_not_create_new_product(self):
        from datetime import date

        from apps.configurator.models import Act, Configuration

        act = Act.objects.create(number='ACT-01', title='ACT', issued_at=date.today())
        response = self.client.post('/api/configurations/', {
            'base_product': self.base.id, 'act': act.id, 'client': self.mijoz.id,
        }, format='json')
        config_id = response.data['id']

        before = Product.objects.count()
        response = full_finalize(self.client, config_id)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Product.objects.count(), before)  # yangi mahsulot yaratilmadi

        configuration = Configuration.objects.get(pk=config_id)
        self.assertEqual(configuration.variant, self.base)

    def test_changed_composition_still_creates_variant(self):
        """Tarkib o'zgartirilsa — bazaviy model emas, yangi variant."""
        response = self.client.post('/api/configurations/', {
            'base_product': self.base.id,
            'items': [
                {'component': self.ssd.id, 'label': 'SSD', 'quantity': 2},
                {'component': self.gpu.id, 'label': 'GPU', 'quantity': 1},
            ],
        }, format='json')
        ready = response.data['ready_variant']
        self.assertIsNone(ready)  # bunday kombinatsiya hali yo'q


class ModifyModeTests(APITestCase):
    """TZ 6.2 (modify): tayyor mahsulot olinadi, ichi o'zgartiriladi,
    yechib olingani omborga qaytadi va bugalterga xabar boradi."""

    def setUp(self):
        from datetime import date

        from apps.configurator.models import Act
        from apps.inventory.models import ProductSpec, StockMovement, Warehouse
        from apps.inventory.services import apply_movement

        self.admin = User.objects.create_user('admin', password='p', role=User.Role.ADMIN)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.act = Act.objects.create(number='ACT-01', title='ACT', issued_at=date.today())
        from apps.clients.models import Client

        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )

        self.base = Product.objects.create(
            sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE,
            sale_price=Decimal('25000000'),
        )
        self.ram4 = Product.objects.create(
            sku='RAM-4', name='RAM 4 GB', kind=Product.Kind.COMPONENT,
            sale_price=Decimal('400000'),
        )
        self.ram8 = Product.objects.create(
            sku='RAM-8', name='RAM 8 GB', kind=Product.Kind.COMPONENT,
            sale_price=Decimal('700000'),
        )
        ProductSpec.objects.create(
            product=self.base, component=self.ram4, label='RAM', quantity=1,
        )
        # Omborda: 2 dona tayyor HP 880 va 3 dona RAM 8
        for product, quantity in [(self.base, 2), (self.ram8, 3)]:
            apply_movement(
                product=product, warehouse=self.warehouse,
                type=StockMovement.Type.IN, quantity=Decimal(quantity),
            )
        # Admin bilan: konfiguratsiya tahriri ham (engineer ishi), finalize ham
        # (sales bosqichi) bitta testda ketadi — rol chegaralari alohida testlarda
        self.client.force_authenticate(self.admin)

    def _stock(self, product):
        from apps.inventory.services import available_quantity

        return available_quantity(product, self.warehouse)

    def _modify_config(self):
        """RAM 4 yechiladi, o'rniga RAM 8 qo'yiladi."""
        response = self.client.post('/api/configurations/', {
            'base_product': self.base.id, 'warehouse': self.warehouse.id,
            'act': self.act.id, 'mode': 'modify', 'client': self.mijoz.id,
            'items': [{'component': self.ram8.id, 'label': 'RAM', 'quantity': 1}],
        }, format='json')
        return response.data['id']

    def test_changes_endpoint_shows_diff(self):
        config_id = self._modify_config()
        response = self.client.get(f'/api/configurations/{config_id}/changes/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['added'][0]['name'], 'RAM 8 GB')
        self.assertEqual(response.data['removed'][0]['name'], 'RAM 4 GB')
        self.assertEqual(Decimal(response.data['removed'][0]['unit_price']), Decimal('400000'))

    def test_finalize_moves_stock_and_returns_removed_part(self):
        from apps.core.models import Notification

        bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        config_id = self._modify_config()
        # #4: yechilgan qism narxi endi yig'ish (assemble) bosqichida beriladi
        response = full_finalize(
            self.client, config_id, removals={str(self.ram4.id): '350000'},
        )
        self.assertEqual(response.status_code, 200, response.data)

        # Ombor: HP 880 2->1, RAM 8 3->2, RAM 4 0->1 — §1.3: variant kirimi yo'q
        self.assertEqual(self._stock(self.base), Decimal('1'))
        self.assertEqual(self._stock(self.ram8), Decimal('2'))
        self.assertEqual(self._stock(self.ram4), Decimal('1'))

        # Yechib olingani narxi bilan yozildi (o'zgartirilgan narx)
        removal = response.data['removals'][0]
        self.assertEqual(removal['component_name'], 'RAM 4 GB')
        self.assertEqual(Decimal(removal['unit_price']), Decimal('350000'))

        # Xabar faqat bugalterga: ACT bilan, yechib olinganlar ro'yxati
        # (user'siz umumiy xabar hammaga ko'rinardi — §10.10 tuzatmasi)
        note = Notification.objects.get(entity='Configuration', user=bugalter)
        self.assertIn('ACT-01', note.title)
        self.assertIn('RAM 4 GB', note.message)

    def test_assemble_blocked_when_no_ready_unit_in_stock(self):
        """#4: modify'da yig'ish (assemble) bazaviy mahsulot yo'q bo'lsa 400."""
        from apps.inventory.models import StockMovement
        from apps.inventory.services import apply_movement

        config_id = self._modify_config()
        apply_movement(  # tayyor mahsulotni tugatamiz
            product=self.base, warehouse=self.warehouse,
            type=StockMovement.Type.OUT, quantity=Decimal('2'),
        )
        walk_to_approved(self.client, config_id)
        response = self.client.post(f'/api/configurations/{config_id}/assemble/')
        self.assertEqual(response.status_code, 400)
        self.assertIn('HP 880', str(response.data))
        # Yig'ilmagan konfiguratsiya yakunlanmaydi ham
        response = self.client.post(f'/api/configurations/{config_id}/finalize/')
        self.assertEqual(response.status_code, 400)

    def test_assemble_blocked_when_added_part_missing(self):
        from apps.inventory.models import StockMovement
        from apps.inventory.services import apply_movement

        config_id = self._modify_config()
        apply_movement(  # RAM 8 tugadi
            product=self.ram8, warehouse=self.warehouse,
            type=StockMovement.Type.OUT, quantity=Decimal('3'),
        )
        walk_to_approved(self.client, config_id)
        response = self.client.post(f'/api/configurations/{config_id}/assemble/')
        self.assertEqual(response.status_code, 400)
        self.assertIn('RAM 8 GB', str(response.data['items']))

    def test_finalize_without_warehouse_falls_back_to_single_active(self):
        """Biznesda bitta ombor — konfiguratsiyada tanlanmagan bo'lsa o'zi olinadi."""
        response = self.client.post('/api/configurations/', {
            'base_product': self.base.id, 'act': self.act.id, 'mode': 'modify',
            'client': self.mijoz.id,
            'items': [{'component': self.ram8.id, 'label': 'RAM', 'quantity': 1}],
        }, format='json')
        config_id = response.data['id']
        response = full_finalize(self.client, config_id)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['warehouse'], self.warehouse.id)
        self.assertEqual(self._stock(self.base), Decimal('1'))

    def test_build_mode_assembles_variant(self):
        """§1.3: build rejimida yig'ish qadami — butlovchi chiqadi, alohida
        katalog yozuvi (variant) yaratilmaydi, shartnoma bazaviy modelda qoladi.
        """
        response = self.client.post('/api/configurations/', {
            'base_product': self.base.id, 'warehouse': self.warehouse.id,
            'act': self.act.id, 'client': self.mijoz.id,  # mode default: build
            'items': [{'component': self.ram8.id, 'label': 'RAM', 'quantity': 1}],
        }, format='json')
        config_id = response.data['id']
        walk_to_approved(self.client, config_id)
        response = self.client.post(f'/api/configurations/{config_id}/assemble/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['assembled'])

        # RAM 8: 3 -> 2 (yig'ishga ketdi) — variant kirimi yo'q (§1.3)
        self.assertEqual(self._stock(self.ram8), Decimal('2'))
        configuration = Configuration.objects.get(pk=config_id)
        self.assertIsNone(configuration.variant)
        # Endi yakunlash o'tadi — mahsulot haqiqatan tayyor
        response = self.client.post(f'/api/configurations/{config_id}/finalize/')
        self.assertEqual(response.status_code, 200, response.data)

    def test_build_shortage_blocks_until_goods_arrive(self):
        """#4: butlovchi yetmasa yig'ish 400 — mol kelgach qayta bosiladi."""
        from apps.inventory.models import StockMovement
        from apps.inventory.services import apply_movement

        response = self.client.post('/api/configurations/', {
            'base_product': self.base.id, 'warehouse': self.warehouse.id,
            'act': self.act.id, 'client': self.mijoz.id,
            'items': [{'component': self.ram8.id, 'label': 'RAM', 'quantity': 10}],
        }, format='json')
        config_id = response.data['id']
        walk_to_approved(self.client, config_id)

        response = self.client.post(f'/api/configurations/{config_id}/assemble/')
        self.assertEqual(response.status_code, 400)
        self.assertIn('RAM 8 GB', str(response.data['items']))
        # Yig'ilmaguncha yakunlash (va demak shartnoma) yo'q
        response = self.client.post(f'/api/configurations/{config_id}/finalize/')
        self.assertEqual(response.status_code, 400)

        # Mol keldi — endi yig'iladi va yakunlanadi
        apply_movement(
            product=self.ram8, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('10'),
        )
        response = self.client.post(f'/api/configurations/{config_id}/assemble/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['assembled'])
        configuration = Configuration.objects.get(pk=config_id)
        self.assertIsNone(configuration.variant)
        response = self.client.post(f'/api/configurations/{config_id}/finalize/')
        self.assertEqual(response.status_code, 200, response.data)
