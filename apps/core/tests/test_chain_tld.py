from decimal import Decimal

from django.utils.timezone import localdate

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.configurator.models import Configuration, ConfigurationItem
from apps.inventory.models import Product, ProductSpec, Warehouse
from apps.procurement.models import Replenishment
from apps.sales.models import Contract, ContractItem


class ChainSingleTldTests(APITestCase):
    """11-§1: "bitta ochiq TLD" zanjirni qo'riqlaydi, eshikni emas."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
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
        # Konfiguratsiyadan tug'ilgan zanjir: CFG approved + SHT active
        self.configuration = Configuration.objects.create(
            base_product=self.base, warehouse=self.warehouse,
            created_by=self.engineer, status=Configuration.Status.APPROVED,
            client=self.mijoz,
        )
        ConfigurationItem.objects.create(
            configuration=self.configuration, component=self.ram,
            label='RAM', quantity=1,
        )
        self.contract = Contract.objects.create(
            client=self.mijoz, configuration=self.configuration,
            status=Contract.Status.ACTIVE, total_amount=Decimal('13440000'),
            created_by=self.sales,
        )
        ContractItem.objects.create(
            contract=self.contract, product=self.base, quantity=1,
            unit_price=Decimal('12000000'),
        )

    def test_contract_gate_closed_for_configuration_chains(self):
        """Konfiguratsiyali shartnomada bu eshik UMUMAN yopiq — CFG biladi."""
        self.client.force_authenticate(self.sales)
        response = self.client.post(
            f'/api/contracts/{self.contract.id}/request-procurement/',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('konfiguratsiyadan tug', str(response.data['detail']))
        self.assertFalse(Replenishment.objects.exists())

    def test_cfg_gate_sees_contract_side_tld(self):
        """Legacy: shartnoma tomonidan ochilgan TLD ham CFG eshigini yopadi."""
        legacy = Replenishment.objects.create(
            warehouse=self.warehouse, contract=self.contract,
            created_by=self.sales,
        )
        self.client.force_authenticate(self.engineer)
        response = self.client.post(
            f'/api/configurations/{self.configuration.id}/request-procurement/',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(legacy.number, str(response.data['detail']))
        self.assertEqual(Replenishment.objects.count(), 1)

    def test_plain_contract_gate_still_works(self):
        """Konfiguratsiyasiz (ombordan sotuv) shartnomada eshik ochiq qoladi."""
        plain = Contract.objects.create(
            client=self.mijoz, status=Contract.Status.ACTIVE,
            total_amount=Decimal('12000000'), created_by=self.sales,
        )
        ContractItem.objects.create(
            contract=plain, product=self.base, quantity=2,
            unit_price=Decimal('6000000'),
        )
        self.client.force_authenticate(self.sales)
        response = self.client.post(
            f'/api/contracts/{plain.id}/request-procurement/',
        )
        self.assertEqual(response.status_code, 201, response.data)
        # Ikkinchi bosishda zanjir tekshiruvi ushlaydi
        response = self.client.post(
            f'/api/contracts/{plain.id}/request-procurement/',
        )
        self.assertEqual(response.status_code, 400)


class RemainingPaymentStepTests(APITestCase):
    """11-§2: qoldiq to'lov — bugalterning ishi, "Yakunlandi" emas."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.admin = User.objects.create_user('adm', password='p', role=User.Role.ADMIN)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        product = Product.objects.create(
            sku='HP-880', name='HP 880', sale_price=Decimal('5000000'),
        )
        # Yetkazilgan, lekin qoldiq to'lanmagan shartnoma (SHT-00056 holati)
        self.contract = Contract.objects.create(
            client=self.mijoz, total_amount=Decimal('116816000'),
            created_by=self.sales, status=Contract.Status.ACTIVE,
            delivered_at=localdate(),
        )
        ContractItem.objects.create(
            contract=self.contract, product=product, quantity=1,
            unit_price=Decimal('104300000'),
        )

    def test_step_becomes_bugalter_remaining_payment(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(f'/api/contracts/{self.contract.id}/roadmap/')
        self.assertEqual(response.data['current_key'], 'completed')
        steps = {s['key']: s for s in response.data['steps']}
        step = steps['completed']
        self.assertEqual(step['state'], 'current')
        self.assertEqual(step['actor']['role'], 'bugalter')
        self.assertEqual(step['label'], "Qoldiq to'lov")

    def test_bugalter_pool_sees_the_chain(self):
        """10-§5 hovuzi + to'g'ri rol: zanjir bugalter ro'yxatida chiqadi."""
        self.client.force_authenticate(self.bugalter)
        response = self.client.get('/api/roadmaps/?state=open')
        self.assertEqual(response.data['count'], 1)

    def test_completed_contract_keeps_original_label(self):
        """Yopilgan shartnomada qadam yana "Yakunlandi" bo'ladi."""
        from django.utils.timezone import now

        from apps.sales.models import ContractPayment

        ContractPayment.objects.create(
            contract=self.contract, amount=Decimal('116816000'),
            paid_at=now(), created_by=self.bugalter,
        )
        Contract.objects.filter(pk=self.contract.pk).update(
            status=Contract.Status.COMPLETED,
        )
        self.client.force_authenticate(self.admin)
        steps = {
            s['key']: s for s in self.client.get(
                f'/api/contracts/{self.contract.id}/roadmap/',
            ).data['steps']
        }
        self.assertEqual(steps['completed']['state'], 'done')
        self.assertEqual(steps['completed']['label'], 'Yakunlandi')
