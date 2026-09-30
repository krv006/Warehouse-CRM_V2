from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.core.choices import Currency
from apps.core.models import CompanyProfile
from apps.inventory.models import Product
from apps.sales.models import Contract, ContractItem


class ContractItemMarginStateTests(APITestCase):
    """27-§2/§3: oddiy qator (konfiguratsiyasiz) — tannarx `Product.cost_price`dan."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.product = Product.objects.create(
            sku='HP-880', name='HP 880', cost_price=Decimal('1000000'),
        )

    def _item(self, unit_price, quantity=1):
        contract = Contract.objects.create(client=self.mijoz, created_by=self.sales)
        return ContractItem.objects.create(
            contract=contract, product=self.product, quantity=quantity, unit_price=unit_price,
        )

    def test_price_below_cost_is_below_cost(self):
        item = self._item(Decimal('900000'))
        self.assertEqual(item.margin_state, 'below_cost')

    def test_price_equal_to_cost_is_below_cost(self):
        """Talab aynan shunday: tannarxga TENG ham qizil, `<` emas `<=`."""
        item = self._item(Decimal('1000000'))
        self.assertEqual(item.margin_state, 'below_cost')

    def test_price_above_cost_below_margin_threshold_is_below_min(self):
        profile = CompanyProfile.load()
        profile.min_margin_percent = Decimal('10')
        profile.save()
        item = self._item(Decimal('1000001'))
        self.assertEqual(item.margin_state, 'below_min')

    def test_price_exactly_at_margin_threshold_is_ok(self):
        """Chegara KIRITILADI: tannarx × 1.10 — allaqachon `ok`."""
        profile = CompanyProfile.load()
        profile.min_margin_percent = Decimal('10')
        profile.save()
        item = self._item(Decimal('1100000'))
        self.assertEqual(item.margin_state, 'ok')

    def test_price_above_margin_threshold_is_ok(self):
        profile = CompanyProfile.load()
        profile.min_margin_percent = Decimal('10')
        profile.save()
        item = self._item(Decimal('1110000'))
        self.assertEqual(item.margin_state, 'ok')

    def test_zero_min_margin_only_below_cost_triggers(self):
        item = self._item(Decimal('1000001'))
        self.assertEqual(item.margin_state, 'ok')

    def test_unknown_cost_price_gives_unknown_not_red(self):
        product = Product.objects.create(sku='NEW-1', name='Yangi mahsulot')
        contract = Contract.objects.create(client=self.mijoz, created_by=self.sales)
        item = ContractItem.objects.create(
            contract=contract, product=product, quantity=1, unit_price=Decimal('500000'),
        )
        self.assertEqual(item.margin_state, 'unknown')

    def test_quantity_change_does_not_change_state(self):
        item = self._item(Decimal('900000'), quantity=1)
        state_one = item.margin_state
        item.quantity = 10
        item.save()
        self.assertEqual(item.margin_state, state_one)

    def test_non_uzs_currency_skips_check(self):
        contract = Contract.objects.create(
            client=self.mijoz, created_by=self.sales, currency=Currency.USD,
        )
        item = ContractItem.objects.create(
            contract=contract, product=self.product, quantity=1, unit_price=Decimal('1'),
        )
        self.assertEqual(item.margin_state, 'unknown')


class ContractMarginAggregateTests(APITestCase):
    """27-§3: shartnoma darajasida ENG YOMON qator bo'yicha jamlanma."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.cheap = Product.objects.create(sku='P1', name='P1', cost_price=Decimal('100'))
        self.new_product = Product.objects.create(sku='P2', name='P2')

    def test_ok_ok_below_cost_gives_below_cost(self):
        contract = Contract.objects.create(client=self.mijoz, created_by=self.sales)
        ContractItem.objects.create(contract=contract, product=self.cheap, quantity=1, unit_price=Decimal('1000'))
        ContractItem.objects.create(contract=contract, product=self.cheap, quantity=1, unit_price=Decimal('1000'))
        ContractItem.objects.create(contract=contract, product=self.cheap, quantity=1, unit_price=Decimal('50'))
        self.assertEqual(contract.margin_state, 'below_cost')

    def test_ok_below_min_ok_gives_below_min(self):
        profile = CompanyProfile.load()
        profile.min_margin_percent = Decimal('50')
        profile.save()
        contract = Contract.objects.create(client=self.mijoz, created_by=self.sales)
        ContractItem.objects.create(contract=contract, product=self.cheap, quantity=1, unit_price=Decimal('1000'))
        ContractItem.objects.create(contract=contract, product=self.cheap, quantity=1, unit_price=Decimal('110'))
        ContractItem.objects.create(contract=contract, product=self.cheap, quantity=1, unit_price=Decimal('1000'))
        self.assertEqual(contract.margin_state, 'below_min')

    def test_unknown_item_among_ok_items_gives_ok_not_unknown(self):
        contract = Contract.objects.create(client=self.mijoz, created_by=self.sales)
        ContractItem.objects.create(
            contract=contract, product=self.new_product, quantity=1, unit_price=Decimal('500000'),
        )
        ContractItem.objects.create(contract=contract, product=self.cheap, quantity=1, unit_price=Decimal('1000'))
        self.assertEqual(contract.margin_state, 'ok')


class MarginVisibilityTests(APITestCase):
    """27-§4: `cost` faqat adminga, `min_price` admin+sales, `margin_state`
    admin+sales+bugalterga — sales tannarxni hech qachon ko'rmaydi."""

    def setUp(self):
        self.admin = User.objects.create_user('adm', password='p', role=User.Role.ADMIN)
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.product = Product.objects.create(
            sku='HP-880', name='HP 880', cost_price=Decimal('1000000'),
        )
        self.contract = Contract.objects.create(
            client=self.mijoz, created_by=self.sales, total_amount=Decimal('900000'),
        )
        ContractItem.objects.create(
            contract=self.contract, product=self.product, quantity=1, unit_price=Decimal('900000'),
        )

    def test_admin_sees_everything(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(f'/api/contracts/{self.contract.id}/')
        item = response.data['items'][0]
        self.assertIn('cost', item)
        self.assertIn('min_price', item)
        self.assertIn('margin_state', item)
        self.assertIn('margin_state', response.data)

    def test_sales_sees_margin_and_min_price_not_cost(self):
        self.client.force_authenticate(self.sales)
        response = self.client.get(f'/api/contracts/{self.contract.id}/')
        item = response.data['items'][0]
        self.assertNotIn('cost', item)
        self.assertIn('min_price', item)
        self.assertIn('margin_state', item)
        self.assertIn('margin_state', response.data)

    def test_bugalter_sees_only_margin_state(self):
        self.client.force_authenticate(self.bugalter)
        response = self.client.get(f'/api/contracts/{self.contract.id}/')
        item = response.data['items'][0]
        self.assertNotIn('cost', item)
        self.assertNotIn('min_price', item)
        self.assertIn('margin_state', item)
        self.assertIn('margin_state', response.data)
