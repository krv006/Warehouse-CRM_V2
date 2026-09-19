from datetime import timedelta
from decimal import Decimal

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db.transaction import atomic
from django.utils.timezone import localdate, now
from io import StringIO


class Command(BaseCommand):
    """Butun tizim uchun bog'langan demo ma'lumotlar to'plami — YANGI oqimlar bilan.

    Hamma narsa haqiqiy servislar orqali yuritiladi, shuning uchun kassa,
    ombor, bron va bildirishnoma raqamlari bir-biriga mos chiqadi. Qamrov:
    texnik tasdiq zanjiri (#4), partiya (#3), yetkazish `ship` (#2),
    TLD/shartnoma admin chegaralari (§11.3, #2-TLD), owner_sales, bron
    (§11.4), SLA (turib qolgan ish), fantom pulsiz qarz (#1), avto-KIR (§4.3).
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
        self._company_profile()
        warehouses = self._warehouses()
        products = self._products(warehouses, users)
        self._base_income()
        act = self._act(users)
        state = {}
        self._configuration_stories(products, warehouses, act, users, state)
        self._contracts(products, users, state)
        self._leads(users, state)
        self._purchases(products, warehouses, users)
        self._replenishments(products, warehouses, users)
        self._loans_and_expenses(users)
        self._make_one_stale(state)
        call_command('check_deadlines', stdout=quiet)

        self._summary()

    # ------------------------------------------------------------------ yordam
    def _wipe(self):
        """Barcha biznes ma'lumotni o'chiradi — mantiq bitta joyda (wipe_data)."""
        call_command('wipe_data', '--yes', stdout=StringIO())
        self.stdout.write(self.style.WARNING(
            "Baza tozalandi (foydalanuvchi akkauntlari saqlab qolindi)."
        ))

    def _users(self):
        from apps.accounts.models import User

        return {
            'admin': User.objects.get(username='admin'),
            'bugalter': User.objects.get(username='bugalter'),
            'sales': User.objects.get(username='sales1'),
            'sales2': User.objects.get(username='sales2'),
            'engineer': User.objects.get(username='engineer'),
            'buyurtmachi': User.objects.get(username='buyurtmachi'),
        }

    def _company_profile(self):
        """Bajaruvchi rekvizitlari + chegaralar (§11.3, TOPSHIRIQ-2 #2)."""
        from apps.core.models import CompanyProfile

        profile = CompanyProfile.load()
        if not profile.name:
            profile.name = 'Ombor Servis MCHJ'
            profile.inn = '305111222'
            profile.phone = '+998712000700'
            profile.email = 'info@ombor.uz'
            profile.address = 'Toshkent shahri, Sergeli tumani, 7-mavze'
            profile.bank_name = 'Kapitalbank, Sergeli filiali'
            profile.mfo = '01088'
            profile.account_number = '20208000900000000001'
            profile.director_name = 'Rustamov K.'
            profile.contract_terms = (
                "To'lov: shartnoma summasining 30% oldindan, qolgani mahsulot "
                "topshirilgach 10 bank kuni ichida. Yetkazib berish muddati "
                "shartnomada ko'rsatilgan kundan boshlab hisoblanadi."
            )
        # Chegaralar: 50 mln dan kichik shartnoma va 5 mln dan kichik TLD
        # admin tasdig'isiz o'tadi — demo shuni ko'rsatadi
        if not profile.admin_approval_threshold:
            profile.admin_approval_threshold = Decimal('50000000')
        if not profile.replenishment_approval_threshold:
            profile.replenishment_approval_threshold = Decimal('5000000')
        profile.save()

    def _warehouses(self):
        from apps.inventory.models import Warehouse

        # Biznesda BITTA ombor bor — ikkinchi ombor yaratilmaydi
        main, _ = Warehouse.objects.get_or_create(
            name='Asosiy ombor', defaults={'address': 'Toshkent, Sergeli 7-mavze'},
        )
        return {'main': main}

    def _products(self, warehouses, users):
        """5 ta mahsulot: 1 bazaviy model + 4 butlovchi, qoldiq bilan."""
        from apps.inventory.models import Product, ProductSpec, StockMovement
        from apps.inventory.services import apply_movement

        rows = [
            # sku, nomi, turi, tannarx, sotuv narxi, reorder, qoldiq
            ('HP-880', 'HP 880 kompyuter', Product.Kind.MACHINE,
             '18000000', '25000000', 2, 8),
            ('SSD-1TB', 'SSD disk 1 TB', Product.Kind.COMPONENT,
             '1200000', '1500000', 5, 10),
            ('GPU-32', 'Videokarta GPU 32', Product.Kind.COMPONENT,
             '4000000', '4500000', 5, 3),
            ('RAM-16', 'Operativ xotira RAM 16 GB', Product.Kind.COMPONENT,
             '700000', '800000', 4, 0),        # tugagan — to'ldirish ro'yxatida
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

        # §11.1: ACT — engineer bosqichi, tarkib egasi o'zi rasmiylashtiradi
        return Act.objects.create(
            number='ACT-0001',
            title='HP 880 tarkibini o\'zgartirish',
            description=(
                '2 ta HP 880 olindi. Har biriga SSD 1 TB qo\'shimcha o\'rnatildi '
                '(jami 2 dona). RAM olib tashlandi va omborga qaytarildi.'
            ),
            issued_at=localdate(),
            created_by=users['engineer'],
        )

    # ------------------------------------------------- konfiguratsiya hikoyalari
    def _configuration_stories(self, products, warehouses, act, users, state):
        """To'rt hikoya — #4 zanjirining har bosqichidan bittadan.

        A: to'liq zanjir (submit -> approve -> assemble -> finalize -> SHT)
        C: sales ko'rigida (pending_sales) — sales navbati
        D: tasdiqlangan + ta'minotda (TLD pending_sales, owner_sales bilan)
        E: engineer chernovigi (draft)
        """
        from apps.clients.models import Client
        from apps.configurator.models import ConfigurationItem, ConfigurationRequest
        from apps.configurator.services import (
            approve_configuration,
            assemble_configuration,
            send_missing_to_procurement,
            submit_configuration,
            take_request,
        )
        from apps.inventory.models import Product
        from apps.inventory.services import (
            create_product_from_order,
            sync_configuration_reservations,
        )
        from apps.procurement import services as procurement
        from apps.procurement.models import Replenishment

        clients = list(Client.objects.order_by('id'))

        # ---------- A: to'liq zanjir — 2 talik partiya, sotuvgacha boradi (#3, #4)
        request_a = ConfigurationRequest.objects.create(
            client=clients[2],
            text='2 ta HP 880: SSD 2 tadan bo\'lsin, RAM keraksiz — olib tashlansin.',
            base_product=products['HP-880'], warehouse=warehouses['main'],
            quantity=2,
            created_by=users['sales'],
        )
        request_a = take_request(request_a, users['engineer'])
        config_a = request_a.configuration
        # Engineer tarkibni mijoz talabiga moslaydi: SSD 2 ta, RAM olib tashlanadi
        config_a.items.filter(component=products['SSD-1TB']).update(quantity=2)
        config_a.items.filter(component=products['RAM-16']).delete()
        submit_configuration(config_a, users['engineer'])
        # YANGI OQIM B1: tasdiq bilan draft shartnoma AVTOMATIK ochiladi
        approve_configuration(config_a, users['sales'], 'Mijoz tarkibga rozi')
        contract_a = config_a.active_contract

        # YANGI OQIM B4: mol to'lovdan keyin — avval pul zanjiri yuriladi
        from apps.sales.services import (
            approve_contract as approve_sht,
            confirm_didox as confirm_didox_sht,
            confirm_payment as pay_sht,
            send_didox as send_didox_sht,
            submit_contract as submit_sht,
        )

        submit_sht(contract_a, users['sales'])
        # B3: Didox ikki qadam — yubordim / Didox tasdiqladi
        send_didox_sht(contract_a, users['bugalter'], 'DDX-2026-0055')
        confirm_didox_sht(contract_a, users['bugalter'])
        contract_a.refresh_from_db()
        if contract_a.status == contract_a.Status.PENDING_ADMIN:
            approve_sht(contract_a, users['admin'], 'Ma\'qul')
            contract_a.refresh_from_db()
        pay_sht(contract_a, users['bugalter'], amount=contract_a.prepayment_amount)
        pay_sht(contract_a, users['bugalter'], amount=Decimal('5000000'))
        contract_a.refresh_from_db()

        # Pul keldi — endi mol: yig'ish va yakunlash (finalize'dagi B6/B7)
        assemble_configuration(config_a, users['engineer'])
        config_a.act = act
        # Shartnoma faol — finalize CFG'ni to'g'ri SOLD qiladi (B7)
        config_a.status = config_a.Status.SOLD
        config_a.save()
        # B6: shartnoma qatori yig'ilgan variantga ko'chadi (son/narx tegilmaydi)
        contract_a.items.filter(product=products['HP-880']).update(
            product=config_a.variant,
        )
        sync_configuration_reservations(config_a)
        from apps.inventory.services import sync_contract_reservations

        sync_contract_reservations(contract_a)
        state['contract_active'] = contract_a
        state['config_a'] = config_a

        # ---------- C: sales ko'rigida — "Konfiguratsiyani ko'rib chiqing"
        request_c = ConfigurationRequest.objects.create(
            client=clients[1],
            text='5 ta o\'quv klassi kompyuteri: GPU kuchli bo\'lsin.',
            base_product=products['HP-880'], warehouse=warehouses['main'],
            quantity=5,
            created_by=users['sales2'],
        )
        request_c = take_request(request_c, users['engineer'])
        submit_configuration(request_c.configuration, users['engineer'])
        state['config_review'] = request_c.configuration

        # ---------- D: tasdiqlangan, yetishmagani buyurtmachida (owner_sales)
        request_d = ConfigurationRequest.objects.create(
            client=clients[0],
            text='HP 880 ga Wi-Fi modul qo\'shib bering.',
            base_product=products['HP-880'], warehouse=warehouses['main'],
            created_by=users['sales'],
        )
        request_d = take_request(request_d, users['engineer'])
        config_d = request_d.configuration
        # Bazada yo'q tovar configuratordan qo'shildi (buyurtma = katalogga kirish)
        wifi = create_product_from_order(
            name='Wi-Fi modul 6E', sku='WIFI-6E',
            kind=Product.Kind.COMPONENT, cost_price=Decimal('350000'),
        )
        products['WIFI-6E'] = wifi
        ConfigurationItem.objects.create(
            configuration=config_d, component=wifi, label='WIFI', quantity=1,
        )
        submit_configuration(config_d, users['engineer'])
        approve_configuration(config_d, users['sales'], 'Wi-Fi bilan ma\'qul')
        # YANGI OQIM B4: ta'minot faqat boshlang'ich to'lovdan keyin —
        # D shartnomasi tez yo'l bilan to'lovgacha yuriladi
        from apps.sales.services import (
            approve_contract as _approve_contract,
            confirm_didox as _confirm_didox,
            confirm_payment as _confirm_payment,
            send_didox as _send_didox,
            submit_contract as _submit_contract,
        )

        contract_d = config_d.active_contract
        _submit_contract(contract_d, users['sales'])
        _send_didox(contract_d, users['bugalter'], 'DDX-2026-0077')
        _confirm_didox(contract_d, users['bugalter'])
        contract_d.refresh_from_db()
        if contract_d.status == contract_d.Status.PENDING_ADMIN:
            _approve_contract(contract_d, users['admin'], 'Ma\'qul')
        contract_d.refresh_from_db()
        _confirm_payment(
            contract_d, users['bugalter'], amount=contract_d.prepayment_amount,
        )
        replenishment_d = send_missing_to_procurement(config_d, users['engineer'])
        # Buyurtmachi narxlarni kiritdi va yubordi -> bugalter (10-§4:
        # to'lov allaqachon kelgan, mijozdan so'raydigan narsa yo'q)
        for item in replenishment_d.items.select_related('product'):
            if not item.unit_price:
                item.unit_price = item.product.cost_price or Decimal('350000')
                item.save()
        procurement.submit(replenishment_d, users['buyurtmachi'])
        state['config_d'] = config_d
        state['replenishment_d'] = replenishment_d

        # ---------- E: engineer chernovigi — hali ko'rikka yuborilmagan
        from apps.configurator.models import Configuration

        draft = Configuration.objects.create(
            client=clients[0], base_product=products['HP-880'],
            warehouse=warehouses['main'], created_by=users['engineer'],
            note='Mijoz hali o\'ylab ko\'rmoqda',
        )
        for sku, label in [('SSD-1TB', 'SSD'), ('GPU-32', 'GPU')]:
            ConfigurationItem.objects.create(
                configuration=draft, component=products[sku], label=label, quantity=1,
            )
        sync_configuration_reservations(draft)

        # Yangi, hali olinmagan zayavka — engineer hovuzi
        ConfigurationRequest.objects.create(
            client=clients[3],
            text='Server yig\'ish kerak: katta xotira, 2 ta protsessor.',
            base_product=products['HP-880'], warehouse=warehouses['main'],
            quantity=1,
            created_by=users['sales2'],
        )

    # ----------------------------------------------------------- shartnomalar
    def _contracts(self, products, users, state):
        """Har bosqichdan bittadan — hammasi haqiqiy servislar orqali."""
        from apps.clients.models import Client
        from apps.inventory.services import sync_contract_reservations
        from apps.sales.models import Contract, ContractItem
        from apps.sales.services import (
            approve_contract,
            confirm_didox,
            confirm_payment,
            send_didox,
            ship_contract,
            submit_contract,
        )

        def didox(contract, number):
            """B3: bugalterning ikki qadami — yubordim / Didox tasdiqladi."""
            send_didox(contract, users['bugalter'], number)
            confirm_didox(contract, users['bugalter'])

        clients = list(Client.objects.order_by('id'))
        hp = products['HP-880']

        def build(client, quantity, note, sales_user=None):
            contract = Contract.objects.create(
                client=client, term_days=90, note=note,
                created_by=sales_user or users['sales'],
            )
            ContractItem.objects.create(
                contract=contract, product=hp, quantity=quantity,
                unit_price=hp.sale_price,
            )
            contract.total_amount = contract.items_total_with_vat
            contract.prepayment_percent = None
            contract.save()
            sync_contract_reservations(contract)
            return contract

        # 1) Chernovik — sales hali yubormagan
        build(clients[0], 1, 'Sales hali yubormadi')

        # 2) Didox navbati (pending_bugalter) — SLA demo uchun keyin eskirtiriladi
        c2 = build(clients[1], 1, 'Bugalter Didoxdan qabul qilishi kutilmoqda')
        submit_contract(c2, users['sales'])
        state['contract_stale'] = c2

        # 3) Katta summa — chegaradan oshadi, ADMINGA boradi (§11.3 demo)
        c3 = build(clients[2], 3, '75 mln + QQS — chegaradan katta, admin ko\'radi')
        submit_contract(c3, users['sales'])
        didox(c3, 'DDX-2026-0031')

        # 4) Kichik summa — chegaradan past, ADMIN CHETLAB O'TILADI (§11.3 demo):
        # bugalter tasdig'i bilan to'g'ri approved, tarixda avtomatik yozuv
        c4 = build(clients[3], 1, 'Kichik summa — admin tasdig\'i talab qilinmadi')
        submit_contract(c4, users['sales'])
        didox(c4, 'DDX-2026-0044')

        # 5) Faol, YETKAZILMAGAN — A-hikoya shartnomasi (YANGI OQIM: pul zanjiri
        # hikoyaning o'zida yurilgan — to'lov yig'ishdan OLDIN keladi, B4).
        # Buyurtmachining "Yetkazing" navbatida turadi (#2)
        c5 = state['contract_active']
        c5.refresh_from_db()
        # Muddat sanog'i ko'rinishi uchun boshlanishini orqaga suramiz (qizil zona)
        c5.start_date = localdate() - timedelta(days=82)
        c5.save()

        # 6) Yetkazilgan va yopilgan — to'liq hayot yo'li (#2: ship)
        c6 = build(clients[3], 1, 'Yetkazilgan va yopilgan shartnoma')
        submit_contract(c6, users['sales'])
        didox(c6, 'DDX-2026-0066')
        confirm_payment(c6, users['bugalter'], amount=c6.total_amount)
        c6.refresh_from_db()
        ship_contract(c6, users['buyurtmachi'])

    def _leads(self, users, state):
        """5 ta og'zaki kelishuv — har bosqichdan bittadan."""
        from apps.clients.models import Client
        from apps.sales.models import Lead

        clients = list(Client.objects.order_by('id'))
        rows = [
            ('Ofis uchun 3 ta kompyuter', Lead.Stage.NEW, '75000000', 2),
            ('O\'quv markazi jihozlash', Lead.Stage.NEGOTIATION, '125000000', 5),
            ('Server yig\'ish bo\'yicha kelishuv', Lead.Stage.VERBAL, '40000000', 0),
            ('Do\'kon uchun kassa kompyuteri', Lead.Stage.CONTRACT, '25000000', 0),
            ('Chegirma so\'ragan mijoz', Lead.Stage.LOST, '25000000', 0),
        ]
        for index, (title, stage, amount, days) in enumerate(rows):
            Lead.objects.create(
                client=clients[index % len(clients)],
                title=title, stage=stage, expected_amount=Decimal(amount),
                # 3-qatordagi VERBAL: aloqa sanasi BUGUN — salesga eslatma tushadi
                next_contact_at=(
                    now() + timedelta(days=days) if days
                    else (now() if stage == Lead.Stage.VERBAL else None)
                ),
                contract=(
                    state['contract_active'] if stage == Lead.Stage.CONTRACT else None
                ),
                created_by=users['sales'],
            )

    def _purchases(self, products, warehouses, users):
        """5 ta qo'lda kirim: UZB ichidan, import (yo'lda), ustav, qabul qilingan,
        muddati yaqin. (TLD receive'dan avto-KIR alohida qo'shiladi — §4.3.)"""
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
        """Yana 3 ta TLD: chernovik, chegara demo (adminsiz) va to'liq o'tgani.

        (To'rtinchisi — konfiguratsiyadan, `_configuration_stories` ichida.)
        """
        from apps.procurement.models import Replenishment, ReplenishmentEvent, ReplenishmentItem
        from apps.procurement import services

        main = warehouses['main']

        # 1) Chernovik — buyurtmachi hali yubormagan
        draft = Replenishment.objects.create(
            warehouse=main, supplier='Etuf MCHJ', created_by=users['buyurtmachi'],
            note='Yetishmayotgan GPU va RAM uchun',
        )
        for sku, quantity, price in [('GPU-32', '5', '4000000'), ('RAM-16', '8', '700000')]:
            ReplenishmentItem.objects.create(
                replenishment=draft, product=products[sku],
                quantity=Decimal(quantity), unit_price=Decimal(price),
            )

        # 2) Kichik summa — TLD chegarasi demo (#2-TLD): bugalter tasdig'i
        # bilan to'g'ri approved, admin chetlab o'tiladi, to'lov kutilmoqda
        small = Replenishment.objects.create(
            warehouse=main, supplier='Texno Savdo MCHJ',
            created_by=users['buyurtmachi'],
            note='Kichik hisob — chegaradan past, admin shart emas',
        )
        ReplenishmentItem.objects.create(
            replenishment=small, product=products['RAM-16'],
            quantity=Decimal('5'), unit_price=Decimal('700000'),
        )
        services.submit(small, users['buyurtmachi'])
        services.approve(small, users['bugalter'], 'Narx mos — chegaradan past')

        # 3) To'liq o'tgani: qarz bilan to'lov (#1: fantom pulsiz) + avto-KIR
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
        # 5 mln qarzga o'tkazib to'laymiz — qarz MAJBURIYAT, kassaga kirim YO'Q
        services.pay(flow, users['bugalter'], debt_amount=Decimal('5000000'))
        services.add_event(
            flow, users['buyurtmachi'],
            stage=ReplenishmentEvent.Stage.CUSTOMS,
            comment='Bojxonada rasmiylashtirilmoqda',
        )
        services.receive(flow, users['bugalter'])  # avto-KIR ham ochiladi (§4.3)

    def _loans_and_expenses(self, users):
        """Shaxsiy qarz (kirim BOR) va xarajat so'rovlari."""
        from apps.finance.models import CashCategory, ExpenseRequest, Loan
        from apps.finance.services import record_transaction

        loan = Loan.objects.create(
            lender_name='Bobur Alimov (shaxsiy)', amount=Decimal('20000000'),
            taken_at=localdate() - timedelta(days=23),
            deadline=localdate() + timedelta(days=7),
            source=Loan.Source.PERSONAL,
            note='Aylanma mablag\' uchun', created_by=users['bugalter'],
        )
        # Shaxsiy qarz — pul haqiqatan keladi, kirim yoziladi (#1 qoidasi)
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

    def _make_one_stale(self, state):
        """SLA demo (#3-TOPSHIRIQ): Didox navbatidagi shartnoma 6 kun turib
        qolgan — admin bosh sahifasida qizil, "Bugalterda N ish kuni" bo'lib
        chiqadi; bugalterning o'z navbatida ham qizil."""
        from apps.sales.models import Contract

        Contract.objects.filter(pk=state['contract_stale'].pk).update(
            status_changed_at=now() - timedelta(days=6),
        )

    def _summary(self):
        from apps.clients.models import Client
        from apps.configurator.models import Configuration, ConfigurationRequest
        from apps.core.models import Notification
        from apps.finance.models import CashTransaction, ExpenseRequest, Loan
        from apps.finance.services import cash_balance
        from apps.inventory.models import Product, StockReservation
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
            ('Bronlar', StockReservation.objects.count()),
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
