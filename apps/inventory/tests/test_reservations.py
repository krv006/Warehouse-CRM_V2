from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.utils.timezone import localdate

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.core.models import Notification
from apps.inventory.models import Product, StockMovement, StockReservation, Warehouse
from apps.inventory.services import (
    apply_movement,
    plannable_quantity,
    sellable_quantity,
)
from apps.sales.models import Contract


class ReservationBasicsTests(APITestCase):
    """§11.4: shartnoma band qiladi (qattiq), konfiguratsiya rejalaydi (yumshoq)."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.admin = User.objects.create_user('adm', password='p', role=User.Role.ADMIN)
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.ssd = Product.objects.create(
            sku='SSD-1TB', name='SSD 1 TB', kind=Product.Kind.COMPONENT,
            sale_price=Decimal('1500000'),
        )
        apply_movement(
            product=self.ssd, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('5'),
        )

    def _make_contract(self, quantity=2):
        self.client.force_authenticate(self.sales)
        return self.client.post('/api/contracts/', {
            'client': self.mijoz.id,
            'items': [{
                'product': self.ssd.id, 'quantity': quantity,
                'unit_price': '1500000',
            }],
        }, format='json').data['id']

    def test_contract_creates_hard_reservation(self):
        self._make_contract(quantity=2)
        reservation = StockReservation.objects.get(kind=StockReservation.Kind.HARD)
        self.assertEqual(reservation.quantity, Decimal('2'))
        self.assertEqual(reservation.status, StockReservation.Status.ACTIVE)
        # Erkin: 5 - 2 = 3; o'z shartnomasiga esa hammasi ochiq
        self.assertEqual(sellable_quantity(self.ssd, self.warehouse), Decimal('3'))
        self.assertEqual(
            sellable_quantity(
                self.ssd, self.warehouse, for_contract=reservation.contract,
            ),
            Decimal('5'),
        )

    def test_partial_reservation_when_stock_short(self):
        """Mol yetmasa shartnoma to'silmaydi — bor qismi band bo'ladi."""
        contract_id = self._make_contract(quantity=8)
        reservation = StockReservation.objects.get(contract_id=contract_id)
        self.assertEqual(reservation.quantity, Decimal('5'))

    def test_second_contract_sees_only_free_stock(self):
        self._make_contract(quantity=4)
        second_id = self._make_contract(quantity=3)
        second = StockReservation.objects.get(contract_id=second_id)
        self.assertEqual(second.quantity, Decimal('1'))  # 5 - 4 = 1

    def test_configuration_soft_reservation_warns_but_does_not_block(self):
        base = Product.objects.create(sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE)
        self.client.force_authenticate(self.engineer)
        self.client.post('/api/configurations/', {
            'base_product': base.id, 'warehouse': self.warehouse.id,
            'items': [{'component': self.ssd.id, 'label': 'SSD', 'quantity': 2}],
        }, format='json')
        soft = StockReservation.objects.get(kind=StockReservation.Kind.SOFT)
        self.assertEqual(soft.quantity, Decimal('2'))
        # Yumshoq bron SOTUVNI to'smaydi — erkin baribir 5
        self.assertEqual(sellable_quantity(self.ssd, self.warehouse), Decimal('5'))
        # Lekin boshqa rejalarga ko'rinadi: rejadan keyin 3
        self.assertEqual(plannable_quantity(self.ssd, self.warehouse), Decimal('3'))

    def test_reject_releases_reservation(self):
        contract_id = self._make_contract(quantity=2)
        self.client.post(f'/api/contracts/{contract_id}/submit/')
        self.client.force_authenticate(self.bugalter)
        self.client.post(f'/api/contracts/{contract_id}/reject/', {'comment': 'x'})

        reservation = StockReservation.objects.get(contract_id=contract_id)
        self.assertEqual(reservation.status, StockReservation.Status.RELEASED)
        self.assertEqual(sellable_quantity(self.ssd, self.warehouse), Decimal('5'))

    def _pay(self, contract_id):
        self.client.post(f'/api/contracts/{contract_id}/submit/')
        self.client.force_authenticate(self.bugalter)
        self.client.post(f'/api/contracts/{contract_id}/approve/')
        self.client.force_authenticate(self.admin)
        self.client.post(f'/api/contracts/{contract_id}/approve/')
        self.client.force_authenticate(self.bugalter)
        return self.client.post(f'/api/contracts/{contract_id}/confirm-payment/')

    def test_payment_keeps_reservation_ship_marks_it(self):
        """#2: to'lov bronni ushlab turadi, chiqim `ship`da bo'ladi."""
        contract_id = self._make_contract(quantity=2)
        response = self._pay(contract_id)
        self.assertEqual(response.status_code, 200, response.data)

        reservation = StockReservation.objects.get(contract_id=contract_id)
        # To'lovdan keyin bron hali FAOL — mol yetkazishni kutmoqda
        self.assertEqual(reservation.status, StockReservation.Status.ACTIVE)
        self.assertEqual(sellable_quantity(self.ssd, self.warehouse), Decimal('3'))

        response = self.client.post(f'/api/contracts/{contract_id}/ship/')
        self.assertEqual(response.status_code, 200, response.data)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, StockReservation.Status.SHIPPED)
        # Qoldiq chiqimda kamaydi: 5 - 2 = 3, bron yo'q
        self.assertEqual(sellable_quantity(self.ssd, self.warehouse), Decimal('3'))

    def test_own_reservation_does_not_block_own_ship(self):
        """Eng nozik joy: shartnoma o'z bronini o'ziga ochiq deb hisoblaydi."""
        contract_id = self._make_contract(quantity=5)  # butun qoldiqni band qiladi
        response = self._pay(contract_id)
        self.assertEqual(response.status_code, 200, response.data)
        response = self.client.post(f'/api/contracts/{contract_id}/ship/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNotNone(
            Contract.objects.get(pk=contract_id).delivered_at,
        )

    def test_manual_release_requires_admin_and_note(self):
        contract_id = self._make_contract(quantity=2)
        reservation = StockReservation.objects.get(contract_id=contract_id)

        # Sales bo'shata olmaydi
        response = self.client.post(f'/api/reservations/{reservation.id}/release/', {
            'note': 'x',
        })
        self.assertEqual(response.status_code, 403)

        self.client.force_authenticate(self.admin)
        # Sababsiz bo'lmaydi
        response = self.client.post(f'/api/reservations/{reservation.id}/release/', {})
        self.assertEqual(response.status_code, 400)
        response = self.client.post(f'/api/reservations/{reservation.id}/release/', {
            'note': 'Mijoz kelishuvdan chiqdi, mol boshqa buyurtmaga kerak',
        })
        self.assertEqual(response.status_code, 200, response.data)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, StockReservation.Status.RELEASED)
        self.assertEqual(reservation.released_by, self.admin)


class ReservationExpiryTests(APITestCase):
    """Muddat o'tsa bron bo'shaydi va hujjat egasiga xabar boradi."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.ssd = Product.objects.create(
            sku='SSD-1TB', name='SSD 1 TB', sale_price=Decimal('1500000'),
        )
        apply_movement(
            product=self.ssd, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('5'),
        )

    def test_expired_reservation_is_freed_with_notification(self):
        self.client.force_authenticate(self.sales)
        contract_id = self.client.post('/api/contracts/', {
            'client': self.mijoz.id,
            'items': [{'product': self.ssd.id, 'quantity': 2, 'unit_price': '1500000'}],
        }, format='json').data['id']

        reservation = StockReservation.objects.get(contract_id=contract_id)
        reservation.expires_at = localdate() - timedelta(days=1)
        reservation.save()

        call_command('check_deadlines', stdout=StringIO())

        reservation.refresh_from_db()
        self.assertEqual(reservation.status, StockReservation.Status.EXPIRED)
        self.assertEqual(sellable_quantity(self.ssd, self.warehouse), Decimal('5'))
        note = Notification.objects.get(entity='StockReservation')
        self.assertEqual(note.user, self.sales)
        self.assertIn('broni muddati tugadi', note.title)

        # Qayta submit — bron qayta uriniladi
        response = self.client.post(f'/api/contracts/{contract_id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(
            StockReservation.objects.filter(
                contract_id=contract_id, status=StockReservation.Status.ACTIVE,
            ).exists()
        )
