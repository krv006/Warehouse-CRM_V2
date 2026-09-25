from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase, TestCase
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.inventory.models import Product
from apps.sales.models import Contract, ContractItem
from apps.sales.services import contract_number, unique_contract_number


class ContractNumberFormatTests(SimpleTestCase):
    """21-§3.5: `NB2309-26` — sales bosh harflari + kun/oy + yil."""

    def test_full_name_initials(self):
        user = User(first_name='Nodir', last_name='Baxtiyorov', username='nodir')
        self.assertEqual(contract_number(user, when=date(2026, 9, 23)), 'NB2309-26')

    def test_cyrillic_name_transliterated(self):
        user = User(first_name='Нодир', last_name='Бахтиёров', username='nodir')
        self.assertEqual(contract_number(user, when=date(2026, 9, 23)), 'NB2309-26')

    def test_username_only_fallback(self):
        user = User(first_name='', last_name='', username='sales1')
        self.assertEqual(contract_number(user, when=date(2026, 9, 23)), 'SA2309-26')

    def test_no_created_by(self):
        self.assertEqual(contract_number(None, when=date(2026, 9, 23)), 'XX2309-26')

    def test_single_word_name(self):
        """Bitta so'zli ism — o'sha so'zning birinchi ikki harfi (username qoidasi bilan bir xil)."""
        user = User(first_name='Nodir', last_name='', username='nodir')
        result = contract_number(user, when=date(2026, 9, 23))
        self.assertEqual(result, 'NO2309-26')


class ContractNumberUniquenessTests(TestCase):
    """Takror — bitta sales bir kunda ikkita shartnoma ochsa: `/2`, `/3` …"""

    def setUp(self):
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )

    def test_dedup_suffix(self):
        candidate = 'NB2309-26'
        first = unique_contract_number(candidate)
        Contract.objects.create(number=first, client=self.mijoz)
        second = unique_contract_number(candidate)
        self.assertEqual(second, 'NB2309-26/2')
        Contract.objects.create(number=second, client=self.mijoz)
        third = unique_contract_number(candidate)
        self.assertEqual(third, 'NB2309-26/3')


class ContractAutoNumberTests(APITestCase):
    """Yangi shartnoma avtomatik `NB…` formatida, eski `SHT-000xx` o'zgarmaydi."""

    def setUp(self):
        self.sales = User.objects.create_user(
            'nodir', password='p', role=User.Role.SALES,
            first_name='Nodir', last_name='Baxtiyorov',
        )
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.product = Product.objects.create(sku='HP-880', name='HP 880')

    def test_new_contract_gets_new_format(self):
        contract = Contract.objects.create(client=self.mijoz, created_by=self.sales)
        self.assertRegex(contract.number, r'^[A-Z]{2}\d{4}-\d{2}(/\d+)?$')

    def test_explicit_old_style_number_untouched(self):
        contract = Contract.objects.create(
            client=self.mijoz, created_by=self.sales, number='SHT-00099',
        )
        self.assertEqual(contract.number, 'SHT-00099')

    def test_auto_opened_contract_number_from_request_owner_not_finalizer(self):
        """21-§3.5: raqam zayavka egasidan, tugmani bosgan engineer/admindan emas."""
        from apps.configurator.models import Configuration, ConfigurationRequest
        from apps.sales.services import create_contract_from_configuration

        engineer = User.objects.create_user(
            'eng', password='p', role=User.Role.ENGINEER,
            first_name='Olim', last_name='Karimov',
        )
        base = Product.objects.create(sku='DELL-1', name='Dell', kind=Product.Kind.MACHINE)
        configuration = Configuration.objects.create(
            base_product=base, client=self.mijoz, created_by=engineer,
        )
        ConfigurationRequest.objects.create(
            client=self.mijoz, text='Dell', created_by=self.sales,
            configuration=configuration, status=ConfigurationRequest.Status.IN_PROGRESS,
        )
        contract = create_contract_from_configuration(configuration, engineer)
        self.assertTrue(contract.number.startswith('NB'))
