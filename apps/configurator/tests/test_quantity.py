from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.configurator.models import Configuration, ConfigurationItem
from apps.inventory.models import Product, StockMovement, StockReservation, Warehouse
from apps.inventory.services import apply_movement, available_quantity
from apps.sales.models import Contract


class ConfigurationQuantityTests(APITestCase):
    """TOPSHIRIQ-2 #3: konfiguratsiya endi partiya yasaydi, bitta dona emas."""

    def setUp(self):
        self.admin = User.objects.create_user('adm', password='p', role=User.Role.ADMIN)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        from apps.clients.models import Client

        # YANGI OQIM B10: approve mijozsiz o'tmaydi — shartnoma ochiladi
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.base = Product.objects.create(
            sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE,
        )
        self.ram = Product.objects.create(
            sku='RAM-16', name='RAM 16', kind=Product.Kind.COMPONENT,
            sale_price=Decimal('700000'),
        )
        self.client.force_authenticate(self.admin)

    def _stock(self, product):
        return available_quantity(product, self.warehouse)

    def _make_config(self, quantity, ram_qty=1):
        configuration = Configuration.objects.create(
            base_product=self.base, warehouse=self.warehouse,
            created_by=self.engineer, quantity=quantity, client=self.mijoz,
        )
        ConfigurationItem.objects.create(
            configuration=configuration, component=self.ram,
            label='RAM', quantity=ram_qty,
        )
        return configuration

    def test_request_quantity_copied_on_take(self):
        """Sales zayavkada miqdorni yozadi — take konfiguratsiyaga ko'chiradi."""
        self.client.force_authenticate(self.sales)
        request_id = self.client.post('/api/configuration-requests/', {
            'text': '100 ta HP 880', 'base_product': self.base.id, 'quantity': 100,
        }, format='json').data['id']
        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configuration-requests/{request_id}/take/')
        configuration = Configuration.objects.get(pk=response.data['configuration'])
        self.assertEqual(configuration.quantity, 100)

    def test_shortage_is_multiplied(self):
        """100 ta kerak, omborda 40 — yetishmovchilik 60 (1 emas)."""
        apply_movement(
            product=self.ram, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('40'),
        )
        configuration = self._make_config(quantity=100)
        item = configuration.items.get()
        self.assertEqual(item.total_needed, 100)
        self.assertEqual(item.shortage, Decimal('60'))

    def test_soft_reservation_covers_batch(self):
        apply_movement(
            product=self.ram, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('10'),
        )
        configuration = self._make_config(quantity=3)
        from apps.inventory.services import sync_configuration_reservations

        sync_configuration_reservations(configuration)
        reservation = StockReservation.objects.get(configuration=configuration)
        self.assertEqual(reservation.quantity, Decimal('3'))

    def test_assemble_builds_whole_batch(self):
        """Yig'ish butun partiyani yasaydi: butlovchi ×3 chiqadi, variant 3 kiradi."""
        apply_movement(
            product=self.ram, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('10'),
        )
        configuration = self._make_config(quantity=3)
        url = f'/api/configurations/{configuration.id}'
        self.client.post(f'{url}/submit/')
        self.client.post(f'{url}/approve/')
        response = self.client.post(f'{url}/assemble/')
        self.assertEqual(response.status_code, 200, response.data)

        self.assertEqual(self._stock(self.ram), Decimal('7'))  # 10 - 3
        configuration.refresh_from_db()
        self.assertEqual(self._stock(configuration.variant), Decimal('3'))

    def test_assemble_blocked_when_batch_does_not_fit(self):
        """3 tadan 2 taga butlovchi bor — qisman yig'ish yo'q: hammasi yoki hech nima."""
        apply_movement(
            product=self.ram, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('2'),
        )
        configuration = self._make_config(quantity=3)
        url = f'/api/configurations/{configuration.id}'
        self.client.post(f'{url}/submit/')
        self.client.post(f'{url}/approve/')
        response = self.client.post(f'{url}/assemble/')
        self.assertEqual(response.status_code, 400)
        self.assertIn('RAM 16', str(response.data['items']))

    def test_auto_contract_carries_batch_quantity(self):
        """Shartnoma qatori: miqdor = partiya, narx bitta donaga — jami ko'paytiriladi."""
        from datetime import date

        from apps.configurator.models import Act

        apply_movement(
            product=self.ram, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('10'),
        )
        configuration = self._make_config(quantity=3)
        act = Act.objects.create(number='ACT-1', title='ACT', issued_at=date.today())
        url = f'/api/configurations/{configuration.id}'
        self.client.post(f'{url}/submit/')
        self.client.post(f'{url}/approve/')
        self.client.post(f'{url}/assemble/')
        response = self.client.post(
            f'{url}/finalize/', {'act': act.id}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)

        contract = Contract.objects.get(pk=response.data['contract']['id'])
        item = contract.items.get()
        self.assertEqual(item.quantity, 3)
        # 3 × 700 000 = 2 100 000 + 12% QQS = 2 352 000
        self.assertEqual(contract.total_amount, Decimal('2352000.00'))

    def test_modify_mode_batch(self):
        """Modify: 2 talik partiya — bazadan 2 chiqadi, variant 2 kiradi."""
        from apps.inventory.models import ProductSpec

        ram4 = Product.objects.create(
            sku='RAM-4', name='RAM 4', kind=Product.Kind.COMPONENT,
            sale_price=Decimal('300000'),
        )
        ProductSpec.objects.create(
            product=self.base, component=ram4, label='RAM', quantity=1,
        )
        for product, quantity in [(self.base, 5), (self.ram, 10)]:
            apply_movement(
                product=product, warehouse=self.warehouse,
                type=StockMovement.Type.IN, quantity=Decimal(quantity),
            )
        configuration = Configuration.objects.create(
            base_product=self.base, warehouse=self.warehouse,
            created_by=self.engineer, quantity=2, mode=Configuration.Mode.MODIFY,
            client=self.mijoz,
        )
        ConfigurationItem.objects.create(
            configuration=configuration, component=self.ram, label='RAM', quantity=1,
        )
        url = f'/api/configurations/{configuration.id}'
        self.client.post(f'{url}/submit/')
        self.client.post(f'{url}/approve/')
        response = self.client.post(f'{url}/assemble/')
        self.assertEqual(response.status_code, 200, response.data)

        # Baza: 5-2=3; RAM16: 10-2=8; RAM4 qaytdi: +2; variant: 2
        self.assertEqual(self._stock(self.base), Decimal('3'))
        self.assertEqual(self._stock(self.ram), Decimal('8'))
        self.assertEqual(self._stock(ram4), Decimal('2'))
        configuration.refresh_from_db()
        self.assertEqual(self._stock(configuration.variant), Decimal('2'))
        removal = configuration.removals.get()
        self.assertEqual(removal.quantity, 2)
        self.assertEqual(removal.unit_price, Decimal('300000'))
