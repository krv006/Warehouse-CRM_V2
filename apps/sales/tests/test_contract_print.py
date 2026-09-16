from datetime import date
from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.configurator.models import Act, Configuration, ConfigurationItem, ConfigurationRequest
from apps.core.models import CompanyProfile
from apps.inventory.models import Product, ProductSpec, Warehouse
from apps.sales.models import Contract


class AutoContractOnFinalizeTests(APITestCase):
    """Finalize'da avtomatik draft shartnoma: bugalterga yuborishdan oldin tayyor."""

    def setUp(self):
        self.sales = User.objects.create_user('sales', password='p', role=User.Role.SALES)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.admin = User.objects.create_user('admin', password='p', role=User.Role.ADMIN)
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.base = Product.objects.create(
            sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE,
        )
        self.ssd = Product.objects.create(
            sku='SSD-1TB', name='SSD 1 TB', kind=Product.Kind.COMPONENT,
            sale_price=Decimal('5000000'),
        )
        ProductSpec.objects.create(
            product=self.base, component=self.ssd, label='SSD', quantity=1,
        )
        self.configuration = Configuration.objects.create(
            base_product=self.base, warehouse=self.warehouse, created_by=self.engineer,
        )
        ConfigurationItem.objects.create(
            configuration=self.configuration, component=self.ssd,
            label='SSD', quantity=1, unit_price=Decimal('5000000'),
        )
        self.act = Act.objects.create(number='ACT-1', title='ACT', issued_at=date.today())
        # Yig'ish uchun butlovchi omborda bo'lsin
        from apps.inventory.models import StockMovement
        from apps.inventory.services import apply_movement

        apply_movement(
            product=self.ssd, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('5'),
        )

    def _finalize(self, **extra):
        # #4 zanjiri: engineer submit -> (admin) approve -> assemble -> finalize
        url = f'/api/configurations/{self.configuration.id}'
        self.client.force_authenticate(self.engineer)
        self.client.post(f'{url}/submit/')
        self.client.force_authenticate(self.admin)
        self.client.post(f'{url}/approve/')
        self.client.force_authenticate(self.engineer)
        self.client.post(f'{url}/assemble/')
        return self.client.post(
            f'{url}/finalize/', {'act': self.act.id, **extra}, format='json',
        )

    def test_contract_created_with_client_from_request(self):
        """ZVK'da mijoz bo'lsa finalize shartnomani o'zi ochadi — QQS bilan."""
        ConfigurationRequest.objects.create(
            client=self.mijoz, text='HP 880 kerak', created_by=self.sales,
            configuration=self.configuration,
        )
        response = self._finalize()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNotNone(response.data['contract'])

        contract = Contract.objects.get(pk=response.data['contract']['id'])
        self.assertEqual(contract.status, Contract.Status.DRAFT)
        self.assertEqual(contract.client, self.mijoz)
        self.assertEqual(contract.configuration, self.configuration)
        item = contract.items.get()
        self.assertEqual(item.quantity, 1)
        self.assertEqual(item.vat_percent, Decimal('12'))
        # 5 000 000 + 12% QQS = 5 600 000 — mijoz to'laydigan summa
        self.assertEqual(contract.total_amount, Decimal('5600000.00'))

    def test_contract_created_with_client_in_body(self):
        """ZVK bo'lmasa ham finalize tanasida mijoz berilsa shartnoma ochiladi."""
        response = self._finalize(client=self.mijoz.id)
        self.assertEqual(response.status_code, 200, response.data)
        contract_id = response.data['contract']['id']
        self.assertEqual(Contract.objects.get(pk=contract_id).client, self.mijoz)

    def test_no_client_no_contract(self):
        """Mijoz aniqlanmasa finalize baribir o'tadi, shartnoma ochilmaydi."""
        response = self._finalize()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(response.data['contract'])
        self.assertFalse(Contract.objects.exists())

    def test_unknown_client_is_400(self):
        response = self._finalize(client=99999)
        self.assertEqual(response.status_code, 400)
        self.assertIn('client', response.data)


class ContractPrintTests(APITestCase):
    """GET /contracts/{id}/print/ — chop etish shakli (rasmdagi modal) ma'lumotlari."""

    def setUp(self):
        self.sales = User.objects.create_user('sales', password='p', role=User.Role.SALES)
        self.bugalter = User.objects.create_user('bugalter', password='p', role=User.Role.BUGALTER)
        self.admin = User.objects.create_user('admin', password='p', role=User.Role.ADMIN)

        profile = CompanyProfile.load()
        profile.name = 'Swiftcore MCHJ'
        profile.inn = '305123456'
        profile.contract_terms = "To'lov 30% oldindan."
        profile.save()

        self.mijoz = Client.objects.create(
            type=Client.Type.LEGAL, company_name='Navoiy Qurilish Servis',
            inn='301111111', jshshir='22223333444455', mfo='00444',
            bank_name='Ipoteka Bank', account_number='20208000600000000002',
            director_name='Karimov B.', phone='+998900000002',
        )
        product = Product.objects.create(
            sku='ADS-1', name='adas', sale_price=Decimal('5000000'),
        )
        self.client.force_authenticate(self.sales)
        self.contract_id = self.client.post('/api/contracts/', {
            'client': self.mijoz.id,
            'items': [{'product': product.id, 'quantity': 1, 'unit_price': '5000000'}],
        }, format='json').data['id']

    def test_print_form_has_everything(self):
        response = self.client.get(f'/api/contracts/{self.contract_id}/print/')
        self.assertEqual(response.status_code, 200, response.data)
        data = response.data

        self.assertEqual(data['company']['name'], 'Swiftcore MCHJ')
        self.assertEqual(data['company']['inn'], '305123456')
        self.assertEqual(data['client']['name'], 'Navoiy Qurilish Servis')
        self.assertEqual(data['client']['inn'], '301111111')

        item = data['items'][0]
        self.assertEqual(item['name'], 'adas')
        self.assertEqual(item['unit'], 'dona')
        self.assertEqual(Decimal(str(item['vat_amount'])), Decimal('600000.00'))
        self.assertEqual(Decimal(str(item['total_with_vat'])), Decimal('5600000.00'))

        totals = data['totals']
        self.assertEqual(Decimal(str(totals['items_total'])), Decimal('5000000.00'))
        self.assertEqual(Decimal(str(totals['vat_total'])), Decimal('600000.00'))
        self.assertEqual(Decimal(str(totals['total'])), Decimal('5600000.00'))
        self.assertEqual(data['terms'], "To'lov 30% oldindan.")

    def test_print_is_403_for_bugalter(self):
        """Chop etish shaklida qator narxlari bor — bugalterga yopiq (TZ)."""
        self.client.force_authenticate(self.bugalter)
        response = self.client.get(f'/api/contracts/{self.contract_id}/print/')
        self.assertEqual(response.status_code, 403)

    def test_print_ok_for_admin(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(f'/api/contracts/{self.contract_id}/print/')
        self.assertEqual(response.status_code, 200)
