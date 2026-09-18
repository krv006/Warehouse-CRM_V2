from decimal import Decimal

from django.utils.timezone import now

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.configurator.models import Configuration, ConfigurationRequest
from apps.core.models import Notification
from apps.inventory.models import (
    Product,
    ProductSpec,
    StockMovement,
    StockReservation,
    Warehouse,
)
from apps.inventory.services import apply_movement
from apps.procurement.models import Replenishment
from apps.sales.models import Contract, ContractPayment


class CancelChainTests(APITestCase):
    """B12/B17 (§3.9): zanjirni bekor qilish — SHT, CFG, ZVK, bronlar birga."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.sales2 = User.objects.create_user('sal2', password='p', role=User.Role.SALES)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
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
            sale_price=Decimal('700000'),
        )
        ProductSpec.objects.create(
            product=self.base, component=self.ram, label='RAM', quantity=1,
        )
        apply_movement(
            product=self.ram, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('10'),
        )

    def _approved_chain(self):
        """ZVK -> take -> submit -> approve: SHT ochilgan, bronlar turibdi."""
        self.client.force_authenticate(self.sales)
        request_id = self.client.post('/api/configuration-requests/', {
            'text': '2 ta HP 880', 'base_product': self.base.id,
            'client': self.mijoz.id, 'quantity': 2,
        }, format='json').data['id']
        self.client.force_authenticate(self.engineer)
        take = self.client.post(f'/api/configuration-requests/{request_id}/take/')
        configuration = Configuration.objects.get(pk=take.data['configuration'])
        self.client.post(f'/api/configurations/{configuration.id}/submit/')
        self.client.force_authenticate(self.sales)
        self.client.post(f'/api/configurations/{configuration.id}/approve/')
        configuration.refresh_from_db()
        return (
            ConfigurationRequest.objects.get(pk=request_id),
            configuration,
            configuration.active_contract,
        )

    def test_cancel_from_request_closes_everything(self):
        """B17: sales zayavkadan bekor qiladi — uchala hujjat va bron yopiladi."""
        request_obj, configuration, contract = self._approved_chain()
        Notification.objects.all().delete()
        response = self.client.post(
            f'/api/configuration-requests/{request_obj.id}/cancel/',
            {'reason': 'Mijoz fikridan qaytdi'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['cancelled']['contract'], contract.number)

        request_obj.refresh_from_db()
        configuration.refresh_from_db()
        contract.refresh_from_db()
        self.assertEqual(request_obj.status, ConfigurationRequest.Status.CANCELLED)
        self.assertEqual(configuration.status, Configuration.Status.CANCELLED)
        self.assertEqual(contract.status, Contract.Status.CANCELLED)
        self.assertFalse(
            StockReservation.objects.filter(
                status=StockReservation.Status.ACTIVE,
            ).exists(),
        )
        # Qatnashchi (engineer) xabar oladi
        self.assertTrue(
            Notification.objects.filter(
                user=self.engineer, title__contains='bekor',
            ).exists(),
        )

    def test_cancel_blocked_after_payment(self):
        """§3.9: pul qabul qilingan — bekor qilinmaydi, qaytarish alohida ish."""
        request_obj, configuration, contract = self._approved_chain()
        Contract.objects.filter(pk=contract.pk).update(status=Contract.Status.ACTIVE)
        ContractPayment.objects.create(
            contract=contract, amount=Decimal('1000000'),
            paid_at=now(), created_by=self.sales,
        )
        response = self.client.post(
            f'/api/contracts/{contract.id}/cancel/',
            {'reason': 'Bekor'}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('Pul qabul qilingan', str(response.data['detail']))
        contract.refresh_from_db()
        self.assertEqual(contract.status, Contract.Status.ACTIVE)

    def test_cancel_requires_reason(self):
        request_obj, configuration, contract = self._approved_chain()
        response = self.client.post(
            f'/api/contracts/{contract.id}/cancel/', {}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('reason', response.data)

    def test_only_owner_sales_or_admin(self):
        """Boshqa sales bekor qila olmaydi; engineer ham (rad etish boshqa narsa)."""
        request_obj, configuration, contract = self._approved_chain()
        self.client.force_authenticate(self.sales2)
        response = self.client.post(
            f'/api/contracts/{contract.id}/cancel/',
            {'reason': 'x'}, format='json',
        )
        self.assertIn(response.status_code, (403, 404))  # ko'rmaydi yoki taqiq
        self.client.force_authenticate(self.engineer)
        response = self.client.post(
            f'/api/configurations/{configuration.id}/cancel/',
            {'reason': 'x'}, format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_paid_tld_left_open_with_warning(self):
        """To'langan/buyurtma qilingan TLD tegilmaydi — ogohlantirish qaytadi."""
        request_obj, configuration, contract = self._approved_chain()
        pending = Replenishment.objects.create(
            warehouse=self.warehouse, configuration=configuration,
            status=Replenishment.Status.PENDING_BUGALTER, created_by=self.engineer,
        )
        ordered = Replenishment.objects.create(
            warehouse=self.warehouse, configuration=configuration,
            status=Replenishment.Status.ORDERED, created_by=self.engineer,
        )
        response = self.client.post(
            f'/api/configuration-requests/{request_obj.id}/cancel/',
            {'reason': 'Mijoz voz kechdi'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        pending.refresh_from_db()
        ordered.refresh_from_db()
        self.assertEqual(pending.status, Replenishment.Status.CANCELLED)
        self.assertEqual(ordered.status, Replenishment.Status.ORDERED)  # tegilmadi
        self.assertTrue(
            any(ordered.number in w for w in response.data['warnings']),
        )
