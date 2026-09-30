from decimal import Decimal

from django.db import connection
from django.test.utils import CaptureQueriesContext
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
        self.buyurtmachi = User.objects.create_user('buy', password='p', role=User.Role.SUPPLIER)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.product = Product.objects.create(
            sku='HP-880', name='HP 880', cost_price=Decimal('1000000'),
        )
        self.contract = Contract.objects.create(
            client=self.mijoz, created_by=self.sales, total_amount=Decimal('900000'),
            # 29-§2: buyurtmachi o'zi yetkazgan shartnomani ko'radi (apps/
            # sales/views.py get_queryset, `delivered_by`) — shu tufayli
            # bu teshik nazariy emas edi
            delivered_by=self.buyurtmachi,
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

    def test_supplier_does_not_see_margin_state(self):
        """29-§2: buyurtmachi bizga TANNARXNI BERADIGAN tomon — ustamamiz
        haqida bilmasligi kerak, garchi ba'zi shartnomalarni ko'rsa ham."""
        self.client.force_authenticate(self.buyurtmachi)
        response = self.client.get(f'/api/contracts/{self.contract.id}/')
        self.assertEqual(response.status_code, 200, response.data)
        item = response.data['items'][0]
        self.assertNotIn('cost', item)
        self.assertNotIn('min_price', item)
        self.assertNotIn('margin_state', item)
        self.assertNotIn('margin_state', response.data)


class MarginControlQueryCountTests(APITestCase):
    """29-§3: marja maydonlari shartnoma detali/ro'yxatini N+1 ga solmasin.

    Eng qimmat holat — `modify` qatorlar: har biri o'z `changes`ini
    (qo'shilgan/yechilgan) `base_product.specs` + `items`dan hisoblaydi.
    """

    def setUp(self):
        from apps.configurator.models import Configuration, ConfigurationItem
        from apps.inventory.models import ProductSpec

        self.admin = User.objects.create_user('adm', password='p', role=User.Role.ADMIN)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.contract = Contract.objects.create(
            client=self.mijoz, created_by=self.admin, total_amount=Decimal('5000000'),
        )
        for i in range(5):
            base = Product.objects.create(
                sku=f'HP-{i}', name=f'HP {i}', kind=Product.Kind.MACHINE,
                cost_price=Decimal('1000000'),
            )
            old_ram = Product.objects.create(
                sku=f'RAM-OLD-{i}', name=f'RAM eski {i}', kind=Product.Kind.COMPONENT,
                cost_price=Decimal('100000'),
            )
            new_ram = Product.objects.create(
                sku=f'RAM-NEW-{i}', name=f'RAM yangi {i}', kind=Product.Kind.COMPONENT,
                cost_price=Decimal('200000'),
            )
            ProductSpec.objects.create(product=base, component=old_ram, label='RAM', quantity=1)
            configuration = Configuration.objects.create(
                base_product=base, created_by=self.admin, mode=Configuration.Mode.MODIFY,
            )
            ConfigurationItem.objects.create(
                configuration=configuration, component=new_ram, label='RAM', quantity=1,
            )
            ContractItem.objects.create(
                contract=self.contract, product=base, configuration=configuration,
                quantity=1, unit_price=Decimal('900000'),
            )

    def test_contract_detail_query_count_is_bounded(self):
        """29-§3: optimizatsiyadan oldin 5 ta `modify` qator ~61 so'rov
        yuborardi (bitta qatorga ~12 ta). Endi: `cached_property`
        (`ContractItem.cost/cost_known/min_price`, `Configuration.
        changes/cost_total/cost_known`) + `Configuration.changes`dagi
        ikki karra `specs` o'qish tuzatildi + `prefetch_related`
        (`sales/views.py`). Qolgan o'sish deyarli chiziqli EMAS — har
        qatorga atigi bittadan `CompanyProfile.load()` (`min_price`) va
        bitta konfiguratsiyaga bittadan (`changes`dagi yechilgan
        butlovchi narxi, `Product.stock_price`) qoladi; buni sinash
        uchun so'rovlar Django darajasida keshlanmaydi (§3 izohi:
        jarayon-darajasidagi kesh test izolyatsiyasini buzardi)."""
        self.client.force_authenticate(self.admin)
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(f'/api/contracts/{self.contract.id}/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data['items']), 5)
        self.assertLessEqual(
            len(ctx.captured_queries), 30,
            f'{len(ctx.captured_queries)} so\'rov — 5 qatorli shartnoma uchun juda ko\'p',
        )

    def test_margin_values_correct_after_optimization(self):
        """cached_property/prefetch qiymatlarni o'zgartirmasligi kerak."""
        self.client.force_authenticate(self.admin)
        response = self.client.get(f'/api/contracts/{self.contract.id}/')
        for item in response.data['items']:
            # base 1 000 000 + yangi RAM 200 000 - eski RAM 100 000 = 1 100 000
            self.assertEqual(item['cost'], Decimal('1100000.00'))
            # narx 900 000 < tannarx 1 100 000
            self.assertEqual(item['margin_state'], 'below_cost')
        self.assertEqual(response.data['margin_state'], 'below_cost')
