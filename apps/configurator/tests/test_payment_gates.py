from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.configurator.models import Configuration, ConfigurationRequest
from apps.inventory.models import (
    Product,
    ProductSpec,
    StockMovement,
    StockReservation,
    Warehouse,
)
from apps.inventory.services import apply_movement
from apps.sales.models import Contract


class PaymentGateTests(APITestCase):
    """YANGI OQIM 2-bosqich: 13–16 qadamlar boshlang'ich to'lovgacha qulflangan."""

    def setUp(self):
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.admin = User.objects.create_user('adm', password='p', role=User.Role.ADMIN)
        User.objects.create_user('buy', password='p', role=User.Role.SUPPLIER)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.base = Product.objects.create(
            sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE,
            sale_price=Decimal('12000000'),
        )
        self.ram = Product.objects.create(
            sku='RAM-16', name='RAM 16', kind=Product.Kind.COMPONENT,
            sale_price=Decimal('1500000'),
        )
        ProductSpec.objects.create(
            product=self.base, component=self.ram, label='RAM', quantity=1,
        )
        apply_movement(
            product=self.ram, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('20'),
        )

    def _take(self, quantity=2):
        self.client.force_authenticate(self.sales)
        request_id = self.client.post('/api/configuration-requests/', {
            'text': f'{quantity} ta HP 880', 'base_product': self.base.id,
            'client': self.mijoz.id, 'quantity': quantity,
        }, format='json').data['id']
        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configuration-requests/{request_id}/take/')
        return (
            Configuration.objects.get(pk=response.data['configuration']),
            ConfigurationRequest.objects.get(pk=request_id),
        )

    def _approved(self, quantity=2):
        configuration, request_obj = self._take(quantity)
        self.client.post(f'/api/configurations/{configuration.id}/submit/')
        self.client.force_authenticate(self.sales)
        self.client.post(f'/api/configurations/{configuration.id}/approve/')
        self.client.force_authenticate(self.engineer)
        configuration.refresh_from_db()
        return configuration, configuration.active_contract

    def _activate(self, contract):
        """Testda to'lov o'rniga to'g'ridan-to'g'ri faollashtirish."""
        Contract.objects.filter(pk=contract.pk).update(
            status=Contract.Status.ACTIVE,
        )

    def test_assemble_and_procurement_blocked_before_payment(self):
        """B4: to'lov kelmaguncha yig'ish ham, ta'minot ham 400 — SHT raqami bilan."""
        configuration, contract = self._approved()
        response = self.client.post(f'/api/configurations/{configuration.id}/assemble/')
        self.assertEqual(response.status_code, 400)
        self.assertIn(contract.number, str(response.data['detail']))

        response = self.client.post(
            f'/api/configurations/{configuration.id}/request-procurement/',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(contract.number, str(response.data['detail']))

    def test_rejected_contract_stops_chain_with_other_message(self):
        """B4: shartnoma rad etilgan — boshqa matn, zanjir to'xtagan."""
        configuration, contract = self._approved()
        Contract.objects.filter(pk=contract.pk).update(
            status=Contract.Status.REJECTED,
        )
        response = self.client.post(f'/api/configurations/{configuration.id}/assemble/')
        self.assertEqual(response.status_code, 400)
        self.assertIn('rad etildi', str(response.data['detail']))

    def test_assemble_passes_after_payment(self):
        configuration, contract = self._approved()
        self._activate(contract)
        response = self.client.post(f'/api/configurations/{configuration.id}/assemble/')
        self.assertEqual(response.status_code, 200, response.data)
        configuration.refresh_from_db()
        self.assertIsNotNone(configuration.assembled_at)

    def test_change_quantity_blocked_after_payment(self):
        """B13: to'lovdan keyin partiya o'zgarmaydi — hech qanday yo'l bilan."""
        configuration, contract = self._approved()
        self._activate(contract)
        response = self.client.post(
            f'/api/configurations/{configuration.id}/change-quantity/',
            {'quantity': 100, 'comment': 'Mijoz oshirdi'}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("to'lov", str(response.data['detail']).lower())
        configuration.refresh_from_db()
        self.assertEqual(configuration.quantity, 2)

    def test_contract_locked_after_payment_even_for_admin(self):
        """B13: to'langan shartnomani admin ham tahrirlay olmaydi."""
        configuration, contract = self._approved()
        self._activate(contract)
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            f'/api/contracts/{contract.id}/', {'note': 'x'}, format='json',
        )
        self.assertEqual(response.status_code, 403)
        item = contract.items.get()
        response = self.client.patch(
            f'/api/contract-items/{item.id}/', {'quantity': 99}, format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_change_quantity_updates_draft_contract(self):
        """B13/B1: pul kelmagan draft shartnoma songa ergashadi — jami qayta yig'iladi."""
        configuration, contract = self._approved(quantity=2)
        self.client.post(
            f'/api/configurations/{configuration.id}/change-quantity/',
            {'quantity': 4, 'comment': 'Mijoz oshirdi'}, format='json',
        )
        contract.refresh_from_db()
        item = contract.items.get()
        self.assertEqual(item.quantity, 4)
        # 4 × 12 000 000 = 48 000 000 + 12% QQS
        self.assertEqual(contract.total_amount, Decimal('53760000.00'))

    def test_request_quantity_syncs_configuration(self):
        """B16: zayavka soni o'zgarsa konfiguratsiya, bron va ZVK birga o'zgaradi."""
        configuration, request_obj = self._take(quantity=2)
        self.client.force_authenticate(self.sales)  # o'z zayavkasi
        response = self.client.patch(
            f'/api/configuration-requests/{request_obj.id}/',
            {'quantity': 5}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        configuration.refresh_from_db()
        request_obj.refresh_from_db()
        self.assertEqual(configuration.quantity, 5)
        self.assertEqual(request_obj.quantity, 5)
        reservation = StockReservation.objects.get(
            configuration=configuration, status=StockReservation.Status.ACTIVE,
        )
        self.assertEqual(reservation.quantity, Decimal('5'))

    def test_request_quantity_locked_after_done(self):
        """B16: yopiq holatdagi zayavkada miqdor o'zgarmaydi — 400."""
        configuration, contract = self._approved()
        request_obj = configuration.requests.get()
        self.assertEqual(request_obj.status, ConfigurationRequest.Status.DONE)
        self.client.force_authenticate(self.sales)
        response = self.client.patch(
            f'/api/configuration-requests/{request_obj.id}/',
            {'quantity': 9}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('quantity', response.data)
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.quantity, 2)
