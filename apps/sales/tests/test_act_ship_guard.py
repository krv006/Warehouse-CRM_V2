from datetime import date
from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.configurator.models import Act, ConfigurationRequest
from apps.core.models import CompanyProfile
from apps.inventory.models import Product, ProductSpec, StockMovement, Warehouse
from apps.inventory.services import apply_movement
from apps.sales.models import Contract, ContractItem


class ActShipGuardTests(APITestCase):
    """20-§3.4: ACT bugalter tasdig'idan o'tmaguncha `ship` mol chiqarmaydi."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.admin = User.objects.create_user('adm', password='p', role=User.Role.ADMIN)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.hp = Product.objects.create(
            sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE,
            sale_price=Decimal('12000000'),
        )
        self.part = Product.objects.create(
            sku='NVME-1', name='Samsung NVMe', kind=Product.Kind.COMPONENT,
            sale_price=Decimal('900000'),
        )
        ProductSpec.objects.create(product=self.hp, component=self.part, label='NVMe', quantity=1)
        apply_movement(
            product=self.part, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('50'),
        )
        # 21-§1.3: bu testdagi zayavka tarkibi zavod spetsifikatsiyasiga teng
        # qoladi (engineer hech narsa o'zgartirmaydi) — bunday holatda yig'ish
        # shart emas, ship bevosita bazaviy modelning o'z qoldig'idan chiqaradi
        apply_movement(
            product=self.hp, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('5'),
        )
        profile = CompanyProfile.load()
        profile.admin_approval_threshold = Decimal('0')
        profile.save()

    def _pay(self, contract):
        from apps.sales.services import approve_contract, confirm_didox, confirm_payment, send_didox

        self.client.force_authenticate(self.sales)
        response = self.client.post(f'/api/contracts/{contract.id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)
        contract.refresh_from_db()
        approve_contract(contract, self.bugalter)
        contract.refresh_from_db()
        if contract.status == Contract.Status.PENDING_ADMIN:
            approve_contract(contract, self.admin)
            contract.refresh_from_db()
        send_didox(contract, self.admin, 'DDX-1')
        confirm_didox(contract, self.admin)
        contract.refresh_from_db()
        confirm_payment(contract, self.admin, amount=contract.total_amount)
        contract.refresh_from_db()

    def _finalized_configuration(self, act_status=Act.Status.PENDING_BUGALTER):
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

        act = Act.objects.create(
            number='ACT-0001', title='ACT', issued_at=date.today(), created_by=self.engineer,
        )
        response = self.client.post(
            f'/api/configurations/{configuration.id}/finalize/', {'act': act.id}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        # `finalize` o'zi avtomatik pending_bugalter'ga yuboradi — testda
        # kerakli holatga to'g'ridan o'rnatamiz (approved/rejected stsenariylari uchun)
        act.status = act_status
        act.save(update_fields=['status'])
        contract.refresh_from_db()
        configuration.refresh_from_db()
        return configuration, contract, act

    def test_ship_blocked_when_act_pending_bugalter(self):
        configuration, contract, act = self._finalized_configuration(Act.Status.PENDING_BUGALTER)
        self.client.force_authenticate(self.sales)
        response = self.client.post(f'/api/contracts/{contract.id}/ship/')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(int(response.data['acts'][0]['id']), act.id)
        contract.refresh_from_db()
        self.assertIsNone(contract.delivered_at)

    def test_ship_blocked_when_act_rejected(self):
        _configuration, contract, _act = self._finalized_configuration(Act.Status.REJECTED)
        self.client.force_authenticate(self.sales)
        response = self.client.post(f'/api/contracts/{contract.id}/ship/')
        self.assertEqual(response.status_code, 400, response.data)

    def test_ship_succeeds_when_act_approved(self):
        _configuration, contract, _act = self._finalized_configuration(Act.Status.APPROVED)
        self.client.force_authenticate(self.sales)
        response = self.client.post(f'/api/contracts/{contract.id}/ship/')
        self.assertEqual(response.status_code, 200, response.data)
        contract.refresh_from_db()
        self.assertIsNotNone(contract.delivered_at)

    def test_acts_approved_field_on_contract(self):
        configuration, contract, _act = self._finalized_configuration(Act.Status.PENDING_BUGALTER)
        self.client.force_authenticate(self.sales)
        response = self.client.get(f'/api/contracts/{contract.id}/')
        self.assertFalse(response.data['acts_approved'])

    def test_ship_not_blocked_for_configuration_less_contract(self):
        """Regressiya: tayyor tovar sotuvi (kind=item, konfiguratsiyasiz) muzlab qolmasin."""
        apply_movement(
            product=self.hp, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('5'),
        )
        contract = Contract.objects.create(
            client=self.mijoz, total_amount=Decimal('5000000'),
            created_by=self.sales, status=Contract.Status.ACTIVE,
        )
        ContractItem.objects.create(
            contract=contract, product=self.hp, quantity=1, unit_price=Decimal('5000000'),
        )
        self.client.force_authenticate(self.sales)
        response = self.client.post(f'/api/contracts/{contract.id}/ship/')
        self.assertEqual(response.status_code, 200, response.data)
