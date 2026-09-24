from datetime import timedelta
from decimal import Decimal

from django.utils.timezone import localdate, now

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.configurator.models import Configuration, ConfigurationRequest
from apps.finance.models import ExpenseRequest, Loan
from apps.finance.services import ensure_default_categories, get_category
from apps.inventory.models import Product, Warehouse
from apps.procurement.models import Replenishment
from apps.sales.models import Contract, Lead


class MyWorkTests(APITestCase):
    """EGALIK §2: navbat va hisoblagich bitta funksiyadan — raqamlar mos."""

    def setUp(self):
        ensure_default_categories()
        self.admin = User.objects.create_user('adm', password='p', role=User.Role.ADMIN)
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.other_sales = User.objects.create_user('sal2', password='p', role=User.Role.SALES)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.buyurtmachi = User.objects.create_user(
            'buy', password='p', role=User.Role.SUPPLIER,
        )
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )

    def _work(self, user):
        self.client.force_authenticate(user)
        return self.client.get('/api/my-work/').data

    def _counts(self, user):
        self.client.force_authenticate(user)
        return self.client.get('/api/sidebar-counts/').data

    def test_sales_sees_own_contracts_only(self):
        Contract.objects.create(client=self.mijoz, created_by=self.sales)  # draft
        Contract.objects.create(
            client=self.mijoz, created_by=self.sales, status=Contract.Status.REJECTED,
        )
        Contract.objects.create(client=self.mijoz, created_by=self.other_sales)
        Contract.objects.create(  # amal kutilmaydigan holat — sanalmaydi
            client=self.mijoz, created_by=self.sales,
            status=Contract.Status.PENDING_BUGALTER,
        )
        work = self._work(self.sales)
        self.assertEqual(work['counts']['contracts'], 2)
        reasons = {row['reason'] for row in work['items'] if row['section'] == 'contracts'}
        self.assertEqual(reasons, {'draft_to_submit', 'fix_and_resubmit'})

    def test_lead_contact_due_counted(self):
        Lead.objects.create(
            client=self.mijoz, title='Bugungi', created_by=self.sales,
            next_contact_at=now(),
        )
        Lead.objects.create(  # kelajakdagi — sanalmaydi
            client=self.mijoz, title='Uzoq', created_by=self.sales,
            next_contact_at=now() + timedelta(days=5),
        )
        Lead.objects.create(  # boshqa sales'niki — sanalmaydi
            client=self.mijoz, title='Begona', created_by=self.other_sales,
            next_contact_at=now(),
        )
        self.assertEqual(self._counts(self.sales)['leads'], 1)

    def test_bugalter_contract_queue(self):
        Contract.objects.create(
            client=self.mijoz, created_by=self.sales,
            status=Contract.Status.PENDING_BUGALTER,
        )
        Contract.objects.create(
            client=self.mijoz, created_by=self.sales, status=Contract.Status.APPROVED,
        )
        counts = self._counts(self.bugalter)
        self.assertEqual(counts['contracts'], 2)
        self.assertEqual(counts['leads'], 0)

    def test_engineer_requests_and_configurations(self):
        ConfigurationRequest.objects.create(text='yangi', created_by=self.sales)
        ConfigurationRequest.objects.create(
            text='meniki', created_by=self.sales,
            status=ConfigurationRequest.Status.IN_PROGRESS, taken_by=self.engineer,
        )
        ConfigurationRequest.objects.create(  # boshqa engineer olgan — sanalmaydi
            text='begona', created_by=self.sales,
            status=ConfigurationRequest.Status.IN_PROGRESS,
            taken_by=User.objects.create_user('eng2', password='p', role=User.Role.ENGINEER),
        )
        base = Product.objects.create(sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE)
        Configuration.objects.create(
            base_product=base, warehouse=self.warehouse, created_by=self.engineer,
        )
        counts = self._counts(self.engineer)
        self.assertEqual(counts['requests'], 2)
        self.assertEqual(counts['configurations'], 1)

    def test_supplier_queue_and_low_stock(self):
        Replenishment.objects.create(
            warehouse=self.warehouse, created_by=self.buyurtmachi,
        )
        Replenishment.objects.create(
            warehouse=self.warehouse, created_by=self.buyurtmachi,
            status=Replenishment.Status.ORDERED,
        )
        Replenishment.objects.create(  # tasdiq bosqichi — buyurtmachining ishi emas
            warehouse=self.warehouse, created_by=self.buyurtmachi,
            status=Replenishment.Status.PENDING_BUGALTER,
        )
        Product.objects.create(sku='GPU-1', name='GPU')  # qoldiq 0 — low stock
        counts = self._counts(self.buyurtmachi)
        self.assertEqual(counts['replenishments'], 2)
        self.assertEqual(counts['low_stock'], 1)

    def test_needs_price_count_for_supplier_only(self):
        """QOLGAN-ISHLAR-2 §6: yon paneldagi "Narx kutilmoqda" sanog'i."""
        from apps.configurator.models import Configuration, ConfigurationItem

        base = Product.objects.create(sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE)
        component = Product.objects.create(sku='RAM-16', name='RAM 16')  # narxsiz
        configuration = Configuration.objects.create(
            base_product=base, warehouse=self.warehouse, client=self.mijoz,
            status=Configuration.Status.DRAFT, created_by=self.engineer,
        )
        ConfigurationItem.objects.create(
            configuration=configuration, component=component, label='RAM', quantity=1,
        )
        self.assertEqual(self._counts(self.buyurtmachi)['needs_price'], 1)
        self.assertEqual(self._counts(self.admin)['needs_price'], 0)
        self.assertEqual(self._counts(self.sales)['needs_price'], 0)

    def test_bugalter_sees_delivered_active_contract_awaiting_balance(self):
        """19-§2: yetkazilgan-u qoldiq to'lanmagan ACTIVE — bugalter navbatida."""
        Contract.objects.create(  # yetkazilgan — bugalter navbatida
            client=self.mijoz, created_by=self.sales,
            status=Contract.Status.ACTIVE, delivered_at=now(),
        )
        Contract.objects.create(  # hali yetkazilmagan — bu hali sales ishi
            client=self.mijoz, created_by=self.sales,
            status=Contract.Status.ACTIVE,
        )
        Contract.objects.create(  # yopilgan — hech kimning navbatida emas
            client=self.mijoz, created_by=self.sales,
            status=Contract.Status.COMPLETED, delivered_at=now(),
        )
        self.assertEqual(self._counts(self.bugalter)['contracts'], 1)
        reasons = {
            row['reason'] for row in self._work(self.bugalter)['items']
            if row['section'] == 'contracts'
        }
        self.assertEqual(reasons, {'awaiting_balance'})

        # Sales tomoniga tegilmadi — hali yetkazilmagan ACTIVE hamon uniki
        self.assertEqual(self._counts(self.sales)['contracts'], 1)
        sales_reasons = {
            row['reason'] for row in self._work(self.sales)['items']
            if row['section'] == 'contracts'
        }
        self.assertEqual(sales_reasons, {'ship_contract'})

    def test_sales_client_approval_only_own(self):
        Replenishment.objects.create(
            warehouse=self.warehouse, status=Replenishment.Status.PENDING_SALES,
            owner_sales=self.sales,
        )
        Replenishment.objects.create(
            warehouse=self.warehouse, status=Replenishment.Status.PENDING_SALES,
            owner_sales=self.other_sales,
        )
        self.assertEqual(self._counts(self.sales)['replenishments'], 1)
        self.assertEqual(self._counts(self.other_sales)['replenishments'], 1)

    def test_admin_expense_and_loans(self):
        ExpenseRequest.objects.create(
            category=get_category('rent'), amount=Decimal('500000'),
            purpose='Arenda', requested_by=self.bugalter,
        )
        Loan.objects.create(
            lender_name='Bobur aka', amount=Decimal('5000000'),
            taken_at=localdate() - timedelta(days=55),
            deadline=localdate() + timedelta(days=5),
        )
        Loan.objects.create(  # muddati uzoq — sanalmaydi
            lender_name='Karim aka', amount=Decimal('1000000'),
            taken_at=localdate(), deadline=localdate() + timedelta(days=40),
        )
        counts = self._counts(self.admin)
        self.assertEqual(counts['expense_requests'], 1)
        self.assertEqual(counts['loans'], 1)

    def test_sidebar_equals_my_work_counts(self):
        """Ikkala endpoint bitta collect_work'dan — raqamlar aynan bir xil."""
        Contract.objects.create(client=self.mijoz, created_by=self.sales)
        Lead.objects.create(
            client=self.mijoz, title='Bugungi', created_by=self.sales,
            next_contact_at=now(),
        )
        work = self._work(self.sales)
        counts = self._counts(self.sales)
        self.assertEqual(work['counts'], counts)
        # items soni ham counts yig'indisiga teng (low_stock'dan tashqari)
        total = sum(v for k, v in work['counts'].items() if k != 'low_stock')
        self.assertEqual(len(work['items']), total)


class WhoWorksTests(APITestCase):
    """EGALIK §5/§6: xodim ismi va filtri."""

    def setUp(self):
        self.admin = User.objects.create_user('adm', password='p', role=User.Role.ADMIN)
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.sales = User.objects.create_user(
            'sales1', password='p', role=User.Role.SALES,
            first_name='Aziz', last_name='Sobirov',
        )
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.contract = Contract.objects.create(
            client=self.mijoz, created_by=self.sales,
        )

    def test_contract_has_created_by_display_name(self):
        """§6.4: username emas — to'liq ism."""
        self.client.force_authenticate(self.admin)
        response = self.client.get(f'/api/contracts/{self.contract.id}/')
        self.assertEqual(response.data['created_by_name'], 'Aziz Sobirov')

    def test_contract_filter_by_created_by(self):
        other = User.objects.create_user('sales2', password='p', role=User.Role.SALES)
        Contract.objects.create(client=self.mijoz, created_by=other)
        self.client.force_authenticate(self.admin)
        response = self.client.get(f'/api/contracts/?created_by={self.sales.id}')
        self.assertEqual(response.data['count'], 1)

    def test_users_readable_by_bugalter_not_writable(self):
        """§5.3: bugalter xodimlarni to'liq ko'radi, lekin rol bera olmaydi."""
        self.client.force_authenticate(self.bugalter)
        response = self.client.get('/api/users/?role=sales')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)

        response = self.client.post('/api/users/', {
            'username': 'yangi', 'password': 'p', 'role': 'admin',
        }, format='json')
        self.assertEqual(response.status_code, 403)

    def test_users_not_readable_by_sales(self):
        self.client.force_authenticate(self.sales)
        self.assertEqual(self.client.get('/api/users/').status_code, 403)
