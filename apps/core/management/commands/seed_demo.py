from datetime import timedelta
from decimal import Decimal

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db.transaction import atomic
from django.utils.timezone import localdate, now
from io import StringIO


class Command(BaseCommand):
    """Butun tizim uchun bog'langan demo ma'lumotlar to'plami.

    Har bo'limga ~5 tadan tushunarli yozuv: mahsulot, qoldiq, mijoz, lead,
    shartnoma (har xil bosqichda), kirim (har xil turda), to'ldirish hisobi,
    qarz, xarajat so'rovi va eslatmalar. Jarayonlar haqiqiy servislar orqali
    yuritiladi — kassa va ombor raqamlari bir-biriga mos chiqadi.
    """

    help = "To'liq demo: userlar, mijozlar, ombor, shartnomalar, kirim, kassa"

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help="Avval bazadagi barcha biznes ma'lumotni o'chiradi (userlar qoladi)",
        )

    @atomic
    def handle(self, *args, **options):
        from apps.inventory.models import Product

        if options['reset']:
            self._wipe()

        quiet = StringIO()
        call_command('seed_finance', stdout=quiet)
        call_command('seed_users', stdout=quiet)
        call_command('seed_clients', stdout=quiet)

        if Product.objects.filter(sku='HP-880').exists():
            self.stdout.write(self.style.WARNING(
                'Demo ma\'lumotlar allaqachon yuklangan — qayta yozilmadi. Toza qayta yuklash: seed_demo --reset'
            ))
            return

        users = self._users()
        warehouses = self._warehouses()
        products = self._products(warehouses, users)
        self._base_income()
        act = self._act(users)
        self._configurations(products, warehouses, act, users)
        self._requests(users)
        contracts = self._contracts(products, users)
        self._leads(contracts, users)
        self._purchases(products, warehouses, users)
        self._replenishments(products, warehouses, users)
        self._loans_and_expenses(users)
        call_command('check_deadlines', stdout=quiet)

        self._summary()

    # ------------------------------------------------------------------ yordam
    def _wipe(self):
        """Barcha biznes ma'lumotni o'chiradi. Foydalanuvchi akkauntlari qoladi.

        O'chirish tartibi PROTECT bog'lanishlarga mos: avval bolalar, keyin otalar.
        """
        from apps.clients.models import Client
        from apps.configurator.models import (
            Act,
            Configuration,
            ConfigurationItem,
            ConfigurationRemoval,
            ConfigurationRequest,
        )
        from apps.core.models import ActivityLog, Notification
        from apps.finance.models import CashTransaction, ExpenseRequest, Loan
        from apps.inventory.models import (
            Product,
            ProductSpec,
            Stock,
            StockMovement,
            Warehouse,
        )
        from apps.procurement.models import (
            Replenishment,
            ReplenishmentApproval,
            ReplenishmentEvent,
            ReplenishmentItem,
        )
        from apps.purchases.models import Purchase, PurchaseDocument, PurchaseItem
        from apps.sales.models import (
            Contract,
            ContractApproval,
            ContractItem,
            ContractPayment,
            Lead,
        )

        ordered = [
            Notification, ActivityLog,
            CashTransaction, ExpenseRequest,
            ReplenishmentEvent, ReplenishmentApproval, ReplenishmentItem, Replenishment,
            Loan,
            PurchaseDocument, PurchaseItem,
            ContractPayment, ContractApproval, ContractItem,
            Lead,
            ConfigurationRequest, ConfigurationRemoval, ConfigurationItem, Configuration,
            Contract, Purchase,
            Act,
            StockMovement, Stock, ProductSpec, Product,
            Warehouse, Client,
        ]
        for model in ordered:
            model.objects.all().delete()
        self.stdout.write(self.style.WARNING(
            "Baza tozalandi (foydalanuvchi akkauntlari saqlab qolindi)."
        ))

    def _users(self):
        from apps.accounts.models import User

        return {
            'admin': User.objects.get(username='admin'),
            'bugalter': User.objects.get(username='bugalter'),
            'sales': User.objects.get(username='sales1'),
            'engineer': User.objects.get(username='engineer'),
            'buyurtmachi': User.objects.get(username='buyurtmachi'),
        }

    def _warehouses(self):
        from apps.inventory.models import Warehouse

        main, _ = Warehouse.objects.get_or_create(
            name='Asosiy ombor', defaults={'address': 'Toshkent, Sergeli 7-mavze'},
        )
        branch, _ = Warehouse.objects.get_or_create(
            name='Samarqand filiali', defaults={'address': 'Samarqand, Ipak yo\'li 12'},
        )
        return {'main': main, 'branch': branch}

    def _products(self, warehouses, users):
        """5 ta mahsulot: 1 bazaviy model + 4 butlovchi, qoldiq bilan."""
        from apps.inventory.models import Product, ProductSpec, StockMovement
        from apps.inventory.services import apply_movement

        rows = [
            # sku, nomi, turi, tannarx, sotuv narxi, reorder, qoldiq
            ('HP-880', 'HP 880 kompyuter', Product.Kind.MACHINE,
             '18000000', '25000000', 2, 3),
            ('SSD-1TB', 'SSD disk 1 TB', Product.Kind.COMPONENT,
             '1200000', '1500000', 5, 10),
            ('GPU-32', 'Videokarta GPU 32', Product.Kind.COMPONENT,
             '4000000', '4500000', 5, 2),      # kam qolgan — to'ldirish ro'yxatiga tushadi
            ('RAM-16', 'Operativ xotira RAM 16 GB', Product.Kind.COMPONENT,
             '700000', '800000', 4, 0),        # tugagan
            ('CPU-8', 'Protsessor 8 yadro', Product.Kind.COMPONENT,
             '1900000', '2200000', 3, 6),
        ]
        products = {}
        for sku, name, kind, cost, sale, reorder, quantity in rows:
            product = Product.objects.create(
                sku=sku, name=name, kind=kind,
                cost_price=Decimal(cost), sale_price=Decimal(sale),
                reorder_level=reorder,
            )
            products[sku] = product
            if quantity:
                apply_movement(
                    product=product, warehouse=warehouses['main'],
                    type=StockMovement.Type.IN, quantity=Decimal(quantity),
                    reason=StockMovement.Reason.PURCHASE,
                    reference='DEMO', user=users['buyurtmachi'],
                )

        # HP 880 ning zavod tarkibi (TZ 6.1)
        specs = [('SSD-1TB', 'SSD', 1), ('GPU-32', 'GPU', 1),
                 ('RAM-16', 'RAM', 1), ('CPU-8', 'CPU', 1)]
        for sku, label, quantity in specs:
            ProductSpec.objects.create(
                product=products['HP-880'], component=products[sku],
                label=label, quantity=quantity,
            )
        return products

    def _base_income(self):
        """Kassaga boshlang'ich tushum — to'lovlar shu puldan chiqadi."""
        from apps.finance.services import record_transaction

        record_transaction(
            code='ustav_in', amount=Decimal('120000000'), occurred_at=now(),
            description='Ustav kapitali kiritildi (demo)',
        )

    def _act(self, users):
        from apps.configurator.models import Act

        return Act.objects.create(
            number='ACT-0001',
            title='HP 880 tarkibini o\'zgartirish',
            description='Mijoz talabiga ko\'ra SSD va GPU almashtiriladi',
            issued_at=localdate(),
            created_by=users['admin'],
        )

    def _configurations(self, products, warehouses, act, users):
        """2 ta konfiguratsiya: chernovik va yakunlangan (variant bilan)."""
        from apps.clients.models import Client
        from apps.configurator.models import Configuration, ConfigurationItem
        from apps.configurator.services import resolve_variant

        clients = list(Client.objects.order_by('id'))

        draft = Configuration.objects.create(
            client=clients[0], base_product=products['HP-880'],
            warehouse=warehouses['main'], created_by=users['engineer'],
            note='Mijoz hali o\'ylab ko\'rmoqda',
        )
        for sku, label in [('SSD-1TB', 'SSD'), ('GPU-32', 'GPU')]:
            ConfigurationItem.objects.create(
                configuration=draft, component=products[sku], label=label, quantity=1,
            )

        ready = Configuration.objects.create(
            client=clients[2], base_product=products['HP-880'],
            warehouse=warehouses['main'], act=act, created_by=users['engineer'],
            note='Kuchaytirilgan variant',
        )
        for sku, label, quantity in [('SSD-1TB', 'SSD', 2), ('GPU-32', 'GPU', 1),
                                     ('CPU-8', 'CPU', 1)]:
            ConfigurationItem.objects.create(
                configuration=ready, component=products[sku], label=label, quantity=quantity,
            )
        variant, _ = resolve_variant(ready)
        ready.variant = variant
        ready.status = Configuration.Status.READY
        ready.save()

    def _requests(self, users):
        """2 ta zayavka: yangi va bajarilgani (sales -> engineer oqimi)."""
        from apps.clients.models import Client
        from apps.configurator.models import Configuration, ConfigurationRequest

        clients = list(Client.objects.order_by('id'))
        ConfigurationRequest.objects.create(
            client=clients[1],
            text='Client 2 ta kuchli kompyuter xohlaydi: SSD kattaroq, GPU zo\'r bo\'lsin.',
            created_by=users['sales'],
        )
        done = ConfigurationRequest.objects.create(
            client=clients[2],
            text='HP 880 ni SSD 2 ta bilan, protsessor kuchliroq qilib bering.',
            status=ConfigurationRequest.Status.DONE,
            configuration=Configuration.objects.filter(
                status=Configuration.Status.READY,
            ).first(),
            taken_by=users['engineer'],
            created_by=users['sales'],
        )

    def _contracts(self, products, users):
        """5 ta shartnoma — jarayonning har bir bosqichidan bittadan."""
        from apps.clients.models import Client
        from apps.sales.models import Contract, ContractApproval, ContractItem
        from apps.sales.services import confirm_payment

        clients = list(Client.objects.order_by('id'))
        hp = products['HP-880']

        def build(client, quantity, status, note):
            total = hp.sale_price * quantity
            contract = Contract.objects.create(
                client=client, status=status, total_amount=total,
                term_days=90, signed_at=localdate(), note=note,
                created_by=users['sales'],
            )
            ContractItem.objects.create(
                contract=contract, product=hp, quantity=quantity,
                unit_price=hp.sale_price,
            )
            return contract

        contracts = {}
        contracts['draft'] = build(
            clients[0], 1, Contract.Status.DRAFT, 'Sales hali yubormadi',
        )
        contracts['bugalter'] = build(
            clients[1], 2, Contract.Status.PENDING_BUGALTER, 'Bugalter tekshiruvida',
        )

        c3 = build(clients[2], 1, Contract.Status.PENDING_ADMIN, 'Admin tasdig\'ini kutmoqda')
        ContractApproval.objects.create(
            contract=c3, step=ContractApproval.Step.BUGALTER,
            decision=ContractApproval.Decision.APPROVED,
            comment='Bandlar to\'g\'ri', decided_by=users['bugalter'],
        )
        contracts['admin'] = c3

        c4 = build(clients[3], 2, Contract.Status.APPROVED, 'Pul tushishi kutilmoqda')
        for step, user in [(ContractApproval.Step.BUGALTER, users['bugalter']),
                           (ContractApproval.Step.ADMIN, users['admin'])]:
            ContractApproval.objects.create(
                contract=c4, step=step,
                decision=ContractApproval.Decision.APPROVED, decided_by=user,
            )
        contracts['approved'] = c4

        # Faol shartnoma: to'lov haqiqiy servis orqali — kassaga kirim tushadi
        c5 = build(clients[0], 2, Contract.Status.APPROVED, 'Faol shartnoma')
        confirm_payment(c5, users['bugalter'], amount=c5.prepayment_amount)
        c5.refresh_from_db()
        # Muddat sanog'i ko'rinishi uchun boshlanishini orqaga suramiz (8 kun qoldi — qizil)
        c5.start_date = localdate() - timedelta(days=82)
        c5.save()
        contracts['active'] = c5
        return contracts

    def _leads(self, contracts, users):
        """5 ta og'zaki kelishuv — har bosqichdan bittadan."""
        from apps.clients.models import Client
        from apps.sales.models import Lead

        clients = list(Client.objects.order_by('id'))
        rows = [
            ('Ofis uchun 3 ta kompyuter', Lead.Stage.NEW, '75000000', 2),
            ('O\'quv markazi jihozlash', Lead.Stage.NEGOTIATION, '125000000', 5),
            ('Server yig\'ish bo\'yicha kelishuv', Lead.Stage.VERBAL, '40000000', 1),
            ('Do\'kon uchun kassa kompyuteri', Lead.Stage.CONTRACT, '25000000', 0),
            ('Chegirma so\'ragan mijoz', Lead.Stage.LOST, '25000000', 0),
        ]
        for index, (title, stage, amount, days) in enumerate(rows):
            Lead.objects.create(
                client=clients[index % len(clients)],
                title=title, stage=stage, expected_amount=Decimal(amount),
                next_contact_at=now() + timedelta(days=days) if days else None,
                contract=contracts['active'] if stage == Lead.Stage.CONTRACT else None,
                created_by=users['sales'],
            )

    def _purchases(self, products, warehouses, users):
        """5 ta kirim: UZB ichidan, import (yo'lda), ustav, qabul qilingan, muddati yaqin."""
        from apps.purchases.models import Purchase, PurchaseDocument, PurchaseItem
        from apps.purchases.services import receive_purchase

        main = warehouses['main']

        def build(type, supplier, status, items, **extra):
            purchase = Purchase.objects.create(
                type=type, supplier=supplier, status=status, warehouse=main,
                created_by=users['bugalter'], **extra,
            )
            for sku, quantity, price in items:
                PurchaseItem.objects.create(
                    purchase=purchase, product=products[sku],
                    quantity=Decimal(quantity), unit_price=Decimal(price),
                )
            return purchase

        build(
            Purchase.Type.LOCAL, 'Texno Savdo MCHJ', Purchase.Status.DRAFT,
            [('RAM-16', '10', '700000')], note='Narx kelishilmoqda',
        )

        importing = build(
            Purchase.Type.IMPORT, 'Shenzhen Tech Co', Purchase.Status.IN_TRANSIT,
            [('GPU-32', '10', '3800000')],
            currency='USD', exchange_rate=Decimal('12800'),
            lead_days=90, ordered_at=localdate() - timedelta(days=20),
            invoice_number='INV-2026-0815',
        )
        PurchaseDocument.objects.create(
            purchase=importing, kind=PurchaseDocument.Kind.CUSTOMS,
            title='Bojxona deklaratsiyasi',
            file=ContentFile(b'DEMO HUJJAT', name='deklaratsiya.pdf'),
            uploaded_by=users['bugalter'],
        )
        PurchaseDocument.objects.create(
            purchase=importing, kind=PurchaseDocument.Kind.INVOICE,
            title='Yetkazib beruvchi invoysi',
            file=ContentFile(b'DEMO INVOYS', name='invoys.pdf'),
            uploaded_by=users['bugalter'],
        )

        build(
            Purchase.Type.USTAV, 'Guangzhou Parts Ltd', Purchase.Status.ORDERED,
            [('CPU-8', '8', '1700000')],
            lead_days=60, ordered_at=localdate() - timedelta(days=5),
            customs_duty=Decimal('1500000'), tax_amount=Decimal('900000'),
        )

        received = build(
            Purchase.Type.LOCAL, 'Mega Elektronika', Purchase.Status.ORDERED,
            [('SSD-1TB', '5', '1150000')],
        )
        receive_purchase(received, users['bugalter'])

        build(
            Purchase.Type.IMPORT, 'Delta Components', Purchase.Status.IN_TRANSIT,
            [('SSD-1TB', '20', '1100000')],
            lead_days=30, ordered_at=localdate() - timedelta(days=25),
            note='Muddati yaqinlashgan import',
        )

    def _replenishments(self, products, warehouses, users):
        """2 ta to'ldirish hisobi: chernovik va to'liq jarayondan o'tgani."""
        from apps.procurement.models import Replenishment, ReplenishmentEvent, ReplenishmentItem
        from apps.procurement import services

        main = warehouses['main']

        draft = Replenishment.objects.create(
            warehouse=main, supplier='Etuf MCHJ', created_by=users['buyurtmachi'],
            note='Yetishmayotgan GPU va RAM uchun',
        )
        for sku, quantity, price in [('GPU-32', '5', '4000000'), ('RAM-16', '8', '700000')]:
            ReplenishmentItem.objects.create(
                replenishment=draft, product=products[sku],
                quantity=Decimal(quantity), unit_price=Decimal(price),
            )

        flow = Replenishment.objects.create(
            warehouse=main, supplier='Orient Supply', created_by=users['buyurtmachi'],
            logistics_cost=Decimal('1500000'), other_cost=Decimal('500000'),
        )
        for sku, quantity, price in [('CPU-8', '4', '1900000'), ('SSD-1TB', '5', '1200000')]:
            ReplenishmentItem.objects.create(
                replenishment=flow, product=products[sku],
                quantity=Decimal(quantity), unit_price=Decimal(price),
            )
        services.submit(flow, users['buyurtmachi'])
        services.approve(flow, users['bugalter'], 'Narxlar bozorga mos')
        services.approve(flow, users['admin'], 'Tasdiqlayman')
        # 5 mln qarzga o'tkazib to'laymiz — ta'minotchi qarzi misoli
        services.pay(flow, users['bugalter'], debt_amount=Decimal('5000000'))
        services.add_event(
            flow, users['buyurtmachi'],
            stage=ReplenishmentEvent.Stage.CUSTOMS,
            comment='Bojxonada rasmiylashtirilmoqda',
        )
        services.receive(flow, users['bugalter'])

    def _loans_and_expenses(self, users):
        """Shaxsiy qarz va xarajat so'rovlari."""
        from apps.finance.models import CashCategory, ExpenseRequest, Loan
        from apps.finance.services import record_transaction

        loan = Loan.objects.create(
            lender_name='Bobur Alimov (shaxsiy)', amount=Decimal('20000000'),
            taken_at=localdate() - timedelta(days=23),
            deadline=localdate() + timedelta(days=7),
            source=Loan.Source.PERSONAL,
            note='Aylanma mablag\' uchun', created_by=users['bugalter'],
        )
        record_transaction(
            code='loan', amount=loan.amount, occurred_at=now(),
            description=f'{loan.lender_name} dan qarz', loan=loan,
            user=users['bugalter'],
        )

        record_transaction(
            code='salary', amount=Decimal('15000000'), occurred_at=now(),
            description='Avgust oyligi (5 xodim)', user=users['bugalter'],
            approved_by=users['admin'],
        )

        rent = CashCategory.objects.get(code='rent')
        meal = CashCategory.objects.get(code='meal')
        ExpenseRequest.objects.create(
            category=rent, amount=Decimal('4000000'),
            purpose='Sentyabr uchun ofis arendasi',
            requested_by=users['bugalter'],
        )
        approved = ExpenseRequest.objects.create(
            category=meal, amount=Decimal('600000'),
            purpose='Jamoa uchun obed', status=ExpenseRequest.Status.APPROVED,
            requested_by=users['bugalter'], decided_by=users['admin'],
            decided_at=now(),
        )
        record_transaction(
            code='meal', amount=approved.amount, occurred_at=now(),
            description=approved.purpose, expense_request=approved,
            user=users['bugalter'], approved_by=users['admin'],
        )

    def _summary(self):
        from apps.clients.models import Client
        from apps.configurator.models import Configuration, ConfigurationRequest
        from apps.core.models import Notification
        from apps.finance.models import CashTransaction, ExpenseRequest, Loan
        from apps.finance.services import cash_balance
        from apps.inventory.models import Product
        from apps.procurement.models import Replenishment
        from apps.purchases.models import Purchase
        from apps.sales.models import Contract, Lead

        rows = [
            ('Mahsulotlar', Product.objects.count()),
            ('Mijozlar', Client.objects.count()),
            ('Leadlar', Lead.objects.count()),
            ('Shartnomalar', Contract.objects.count()),
            ('Konfiguratsiyalar', Configuration.objects.count()),
            ('Zayavkalar', ConfigurationRequest.objects.count()),
            ('Kirimlar', Purchase.objects.count()),
            ("To'ldirish hisoblari", Replenishment.objects.count()),
            ('Qarzlar', Loan.objects.count()),
            ("Xarajat so'rovlari", ExpenseRequest.objects.count()),
            ('Kassa harakatlari', CashTransaction.objects.count()),
            ('Eslatmalar', Notification.objects.count()),
        ]
        self.stdout.write('')
        for name, count in rows:
            self.stdout.write(f'  {name:<22}{count}')
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'Demo tayyor. Kassa qoldig\'i: {cash_balance():,.0f} so\'m'
        ))
        self.stdout.write("Kirish: admin / bugalter / engineer / buyurtmachi / sales1, parol: Ombor2026!")
