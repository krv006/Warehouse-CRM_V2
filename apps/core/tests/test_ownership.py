from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.configurator.models import Configuration, ConfigurationRequest
from apps.inventory.models import Product, Warehouse
from apps.procurement.models import Replenishment
from apps.sales.models import Contract, Lead


class ContractOwnershipTests(APITestCase):
    """EGALIK §3: sales faqat O'Z shartnomasini ko'radi va yuritadi."""

    def setUp(self):
        self.sales_a = User.objects.create_user('sales_a', password='p', role=User.Role.SALES)
        self.sales_b = User.objects.create_user('sales_b', password='p', role=User.Role.SALES)
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.admin = User.objects.create_user('adm', password='p', role=User.Role.ADMIN)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.contract_b = Contract.objects.create(
            client=self.mijoz, created_by=self.sales_b,
        )

    def test_sales_does_not_see_others_contract(self):
        self.client.force_authenticate(self.sales_a)
        self.assertEqual(self.client.get('/api/contracts/').data['count'], 0)
        response = self.client.get(f'/api/contracts/{self.contract_b.id}/')
        self.assertEqual(response.status_code, 404)
        # Tahrir va submit ham yo'q — hujjat umuman ko'rinmaydi
        self.assertEqual(
            self.client.patch(
                f'/api/contracts/{self.contract_b.id}/', {'note': 'x'}, format='json',
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(f'/api/contracts/{self.contract_b.id}/submit/').status_code,
            404,
        )

    def test_bugalter_and_admin_see_everything(self):
        for user in (self.bugalter, self.admin):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get('/api/contracts/').data['count'], 1)
            self.assertEqual(
                self.client.get(f'/api/contracts/{self.contract_b.id}/').status_code,
                200,
            )

    def test_engineer_sees_no_contracts(self):
        self.client.force_authenticate(self.engineer)
        self.assertEqual(self.client.get('/api/contracts/').data['count'], 0)

    def test_submit_requires_ownership_even_for_service(self):
        """§3.4-3: xizmat darajasidagi qo'riqchi — admin esa sales nomidan yubora oladi."""
        from apps.sales.models import ContractItem

        ContractItem.objects.create(
            contract=self.contract_b, product=Product.objects.create(sku='P1', name='P'),
            quantity=1, unit_price=Decimal('100'),
        )
        self.client.force_authenticate(self.admin)
        response = self.client.post(f'/api/contracts/{self.contract_b.id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)

    def test_lead_ownership(self):
        Lead.objects.create(client=self.mijoz, title='B niki', created_by=self.sales_b)
        self.client.force_authenticate(self.sales_a)
        self.assertEqual(self.client.get('/api/leads/').data['count'], 0)
        self.client.force_authenticate(self.sales_b)
        self.assertEqual(self.client.get('/api/leads/').data['count'], 1)


class ConfiguratorOwnershipTests(APITestCase):
    """EGALIK §3: engineer o'zinikini, sales o'z zayavkasidan tug'ilganini ko'radi."""

    def setUp(self):
        self.eng_a = User.objects.create_user('eng_a', password='p', role=User.Role.ENGINEER)
        self.eng_b = User.objects.create_user('eng_b', password='p', role=User.Role.ENGINEER)
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        base = Product.objects.create(sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE)
        self.config_b = Configuration.objects.create(
            base_product=base, warehouse=self.warehouse, created_by=self.eng_b,
        )

    def test_engineer_does_not_see_others_configuration(self):
        self.client.force_authenticate(self.eng_a)
        self.assertEqual(self.client.get('/api/configurations/').data['count'], 0)
        self.assertEqual(
            self.client.get(f'/api/configurations/{self.config_b.id}/').status_code, 404,
        )
        # Boshqaning konfiguratsiyasiga qator ham qo'sha olmaydi
        component = Product.objects.create(sku='SSD-1', name='SSD')
        response = self.client.post('/api/configuration-items/', {
            'configuration': self.config_b.id, 'component': component.id,
            'label': 'SSD', 'quantity': 1,
        }, format='json')
        self.assertEqual(response.status_code, 403)

    def test_sales_sees_configuration_born_from_own_request(self):
        ConfigurationRequest.objects.create(
            text='HP 880', created_by=self.sales, configuration=self.config_b,
        )
        self.client.force_authenticate(self.sales)
        self.assertEqual(self.client.get('/api/configurations/').data['count'], 1)
        self.assertEqual(
            self.client.get(f'/api/configurations/{self.config_b.id}/').status_code, 200,
        )

    def test_engineer_sees_new_requests_and_own_taken(self):
        ConfigurationRequest.objects.create(text='yangi', created_by=self.sales)
        ConfigurationRequest.objects.create(
            text='B olgan', created_by=self.sales,
            status=ConfigurationRequest.Status.IN_PROGRESS, taken_by=self.eng_b,
        )
        self.client.force_authenticate(self.eng_a)
        listing = self.client.get('/api/configuration-requests/').data
        self.assertEqual(listing['count'], 1)  # faqat `new`
        self.client.force_authenticate(self.eng_b)
        self.assertEqual(self.client.get('/api/configuration-requests/').data['count'], 2)

    def test_sales_sees_only_own_requests(self):
        other_sales = User.objects.create_user('sal2', password='p', role=User.Role.SALES)
        ConfigurationRequest.objects.create(text='meniki', created_by=self.sales)
        ConfigurationRequest.objects.create(text='begona', created_by=other_sales)
        self.client.force_authenticate(self.sales)
        self.assertEqual(self.client.get('/api/configuration-requests/').data['count'], 1)


class ReplenishmentVisibilityTests(APITestCase):
    """EGALIK §3.2: ta'minot bo'limi ochiq, sales faqat o'z pending_sales hisobini ko'radi."""

    def setUp(self):
        self.buyurtmachi = User.objects.create_user('buy', password='p', role=User.Role.SUPPLIER)
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.other_sales = User.objects.create_user('sal2', password='p', role=User.Role.SALES)
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.draft = Replenishment.objects.create(
            warehouse=self.warehouse, created_by=self.buyurtmachi,
        )
        self.pending_own = Replenishment.objects.create(
            warehouse=self.warehouse, status=Replenishment.Status.PENDING_SALES,
            owner_sales=self.sales,
        )
        self.pending_other = Replenishment.objects.create(
            warehouse=self.warehouse, status=Replenishment.Status.PENDING_SALES,
            owner_sales=self.other_sales,
        )

    def test_supplier_sees_all(self):
        self.client.force_authenticate(self.buyurtmachi)
        self.assertEqual(self.client.get('/api/replenishments/').data['count'], 3)

    def test_sales_sees_only_own_pending(self):
        self.client.force_authenticate(self.sales)
        listing = self.client.get('/api/replenishments/').data
        self.assertEqual(listing['count'], 1)
        self.assertEqual(listing['results'][0]['id'], self.pending_own.id)
        # Qoralama ham, boshqaning pendingi ham 404
        self.assertEqual(
            self.client.get(f'/api/replenishments/{self.draft.id}/').status_code, 404,
        )
        self.assertEqual(
            self.client.get(f'/api/replenishments/{self.pending_other.id}/').status_code,
            404,
        )
