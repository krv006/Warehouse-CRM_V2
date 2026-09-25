from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.configurator.models import Configuration, ConfigurationRequest, ConfigurationRequestLine
from apps.inventory.models import Product, ProductSpec, StockMovement, Warehouse
from apps.inventory.services import apply_movement
from apps.sales.models import Contract, ContractDocument


class DealActionsTests(APITestCase):
    """16-to'plam: amallar savdo darajasida (§A) va model qo'shish/almashtirish (§B)."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
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
        self.dell = Product.objects.create(
            sku='DELL-7010', name='Dell OptiPlex 7010', kind=Product.Kind.MACHINE,
            sale_price=Decimal('10000000'),
        )
        self.ssd = Product.objects.create(
            sku='SSD-1TB', name='Zapas SSD 1TB', kind=Product.Kind.COMPONENT,
            sale_price=Decimal('900000'),
        )
        self.dell_ram = Product.objects.create(
            sku='DELL-RAM', name='Dell RAM 16GB', kind=Product.Kind.COMPONENT,
            sale_price=Decimal('700000'),
        )
        ProductSpec.objects.create(product=self.hp, component=self.ssd, label='SSD', quantity=1)
        ProductSpec.objects.create(product=self.dell, component=self.dell_ram, label='RAM', quantity=1)
        # HP uchun butlovchi doim yetarli (50 dona) — Dell uchun ATAYLAB
        # HECH QACHON kirim qilinmaydi (qoldiq 0), shu bilan ikkalasi
        # BITTA fizik zaxira uchun raqobatlashmaydi (bron matematikasi
        # murakkablashmaydi) va Dell doim "yetishmaydi" tomonda turadi.
        apply_movement(
            product=self.ssd, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('50'),
        )

    # ------------------------------------------------------------ helpers

    def _single_model_request(self):
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/configuration-requests/', {
            'text': '2 ta HP 880', 'base_product': self.hp.id,
            'client': self.mijoz.id, 'quantity': 2,
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return ConfigurationRequest.objects.get(pk=response.data['id'])

    def _dual_model_request(self):
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/configuration-requests/', {
            'text': '10 ta HP 880 + 5 ta Dell',
            'base_product': self.hp.id, 'client': self.mijoz.id, 'quantity': 10,
            'lines': [
                {'kind': 'model', 'base_product': self.dell.id, 'quantity': 5, 'text': 'Dell'},
            ],
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return ConfigurationRequest.objects.get(pk=response.data['id'])

    def _take(self, request_obj):
        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configuration-requests/{request_obj.id}/take/')
        self.assertEqual(response.status_code, 200, response.data)
        request_obj.refresh_from_db()
        return request_obj

    def _pay(self, contract):
        from apps.sales.services import approve_contract, confirm_didox, confirm_payment, send_didox

        self.client.force_authenticate(self.sales)
        ContractDocument.objects.update_or_create(contract=contract, defaults={'body': '<p>x</p>'})
        response = self.client.post(f'/api/contracts/{contract.id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)
        contract.refresh_from_db()
        approve_contract(contract, self.admin)
        contract.refresh_from_db()
        if contract.status == Contract.Status.PENDING_ADMIN:
            approve_contract(contract, self.admin)
            contract.refresh_from_db()
        send_didox(contract, self.admin, 'DDX-1')
        confirm_didox(contract, self.admin)
        contract.refresh_from_db()
        confirm_payment(contract, self.admin, amount=contract.total_amount)
        contract.refresh_from_db()

    # -------------------------------------------------------------- A1/C

    def test_single_model_deal_submit_matches_model_submit(self):
        """A1: bitta modelli ZVKda savdo `submit` = model `submit` natijasi."""
        request_obj = self._take(self._single_model_request())
        configuration = request_obj.configuration

        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configuration-requests/{request_obj.id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)

        configuration.refresh_from_db()
        self.assertEqual(configuration.status, Configuration.Status.PENDING_SALES)

    # ------------------------------------------------------------------ A2

    def test_submit_blocks_all_when_one_not_ready(self):
        """A2: ikki modelli — bittasi tayyor emas → submit 400, hech biri o'zgarmaydi."""
        request_obj = self._take(self._dual_model_request())
        primary = request_obj.configuration
        dell_config = request_obj.lines.get(base_product=self.dell).configuration
        dell_config.items.all().delete()

        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configuration-requests/{request_obj.id}/submit/')
        self.assertEqual(response.status_code, 400, response.data)
        blocked = response.data['blocked']
        self.assertEqual(len(blocked), 1)
        self.assertEqual(blocked[0]['reason'], 'no_items')

        primary.refresh_from_db()
        dell_config.refresh_from_db()
        self.assertEqual(primary.status, Configuration.Status.DRAFT)
        self.assertEqual(dell_config.status, Configuration.Status.DRAFT)

    def test_approve_deal_approves_both_and_opens_one_contract(self):
        """A2: ikki modelli — approve → 2 model approved, 1 ta shartnoma."""
        request_obj = self._take(self._dual_model_request())
        primary = request_obj.configuration
        dell_config = request_obj.lines.get(base_product=self.dell).configuration

        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configuration-requests/{request_obj.id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)

        self.client.force_authenticate(self.sales)
        response = self.client.post(f'/api/configuration-requests/{request_obj.id}/approve/')
        self.assertEqual(response.status_code, 200, response.data)

        primary.refresh_from_db()
        dell_config.refresh_from_db()
        self.assertEqual(primary.status, Configuration.Status.APPROVED)
        self.assertEqual(dell_config.status, Configuration.Status.APPROVED)
        self.assertEqual(Contract.objects.count(), 1)
        self.assertEqual(primary.active_contract.id, dell_config.active_contract.id)

    def test_assemble_deal_partial_success(self):
        """A2: bitta model yig'iladi, ikkinchisida mol yo'q → 200, `pending` to'la."""
        request_obj = self._take(self._dual_model_request())
        primary = request_obj.configuration
        dell_config = request_obj.lines.get(base_product=self.dell).configuration
        # 21-§1.3: tarkib zavod spetsifikatsiyasiga teng bo'lsa yig'ish shart
        # emas (gate `ship`ga ko'chadi) — bu test haqiqiy butlovchi
        # tanqisligini tekshirishi uchun Dell tarkibi ataylab o'zgartiriladi
        dell_config.items.filter(component=self.dell_ram).update(quantity=2)

        self.client.force_authenticate(self.engineer)
        self.client.post(f'/api/configuration-requests/{request_obj.id}/submit/')
        self.client.force_authenticate(self.sales)
        self.client.post(f'/api/configuration-requests/{request_obj.id}/approve/')
        contract = Contract.objects.get()
        self._pay(contract)

        # HP (SSD, 50 dona zaxira) yig'iladi, Dell (RAM, hech qachon
        # kirim qilinmagan) yetishmaydi — setUp'dagi tayyorgarlik yetarli
        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configuration-requests/{request_obj.id}/assemble/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['assembled'], [primary.number])
        self.assertEqual(len(response.data['pending']), 1)
        self.assertEqual(response.data['pending'][0]['number'], dell_config.number)
        self.assertTrue(response.data['pending'][0]['missing'])

    def test_finalize_deal_both_ready_one_act(self):
        """A2: finalize → 2 model `ready`, ikkalasida BITTA ACT."""
        from datetime import date

        from apps.configurator.models import Act

        request_obj = self._take(self._dual_model_request())
        primary = request_obj.configuration
        dell_config = request_obj.lines.get(base_product=self.dell).configuration

        self.client.force_authenticate(self.engineer)
        self.client.post(f'/api/configuration-requests/{request_obj.id}/submit/')
        self.client.force_authenticate(self.sales)
        self.client.post(f'/api/configuration-requests/{request_obj.id}/approve/')
        contract = Contract.objects.get()
        self._pay(contract)
        # Bu testda ikkalasi ham yig'ilishi kerak — Dell uchun ham RAM kiritamiz
        apply_movement(
            product=self.dell_ram, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('10'),
        )

        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configuration-requests/{request_obj.id}/assemble/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(set(response.data['assembled']), {primary.number, dell_config.number})

        act = Act.objects.create(number='ACT-0001', title='ACT', issued_at=date.today())
        response = self.client.post(
            f'/api/configuration-requests/{request_obj.id}/finalize/',
            {'act': act.id}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(set(response.data['finalized']), {primary.number, dell_config.number})

        primary.refresh_from_db()
        dell_config.refresh_from_db()
        self.assertIn(primary.status, (Configuration.Status.READY, Configuration.Status.SOLD))
        self.assertIn(dell_config.status, (Configuration.Status.READY, Configuration.Status.SOLD))
        self.assertEqual(primary.act_id, act.id)
        self.assertEqual(dell_config.act_id, act.id)

    # ------------------------------------------------------------------ A3

    def test_ask_sales_deal_moves_all_models_single_thread(self):
        """A3: `ask-sales` → 2 model ham `pending_clarification`, yozishma bitta."""
        request_obj = self._take(self._dual_model_request())
        primary = request_obj.configuration
        dell_config = request_obj.lines.get(base_product=self.dell).configuration

        self.client.force_authenticate(self.engineer)
        response = self.client.post(
            f'/api/configuration-requests/{request_obj.id}/ask-sales/',
            {'comment': 'Dell narxi qanday bo\'lsin?'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)

        primary.refresh_from_db()
        dell_config.refresh_from_db()
        self.assertEqual(primary.status, Configuration.Status.PENDING_CLARIFICATION)
        self.assertEqual(dell_config.status, Configuration.Status.PENDING_CLARIFICATION)

        primary_resp = self.client.get(f'/api/configurations/{primary.id}/')
        dell_resp = self.client.get(f'/api/configurations/{dell_config.id}/')
        self.assertEqual(len(primary_resp.data['approvals']), 1)
        self.assertEqual(dell_resp.data['approvals'], primary_resp.data['approvals'])

        self.client.force_authenticate(self.sales)
        response = self.client.post(
            f'/api/configuration-requests/{request_obj.id}/answer/',
            {'comment': "12 mln bo'lsin"}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        primary.refresh_from_db()
        dell_config.refresh_from_db()
        self.assertEqual(primary.status, Configuration.Status.DRAFT)
        self.assertEqual(dell_config.status, Configuration.Status.DRAFT)

    # ------------------------------------------------------------------ B2

    def test_add_model_line_opens_configuration_immediately_when_in_progress(self):
        """B2: `in_progress` zayavkaga model qo'shiladi → CFG darhol ochiladi."""
        request_obj = self._take(self._single_model_request())

        self.client.force_authenticate(self.sales)
        response = self.client.post(
            f'/api/configuration-requests/{request_obj.id}/lines/',
            {'kind': 'model', 'base_product': self.dell.id, 'quantity': 3, 'text': 'Qo\'shimcha Dell'},
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIsNotNone(response.data['configuration'])

        line = ConfigurationRequestLine.objects.get(pk=response.data['line']['id'])
        self.assertIsNotNone(line.configuration_id)
        self.assertEqual(line.configuration.status, Configuration.Status.DRAFT)
        self.assertEqual(line.configuration.base_product_id, self.dell.id)

    def test_add_line_blocked_when_new(self):
        """B2 (teskarisi): zayavka hali `new` bo'lsa — chernovik ochilmaydi."""
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/configuration-requests/', {
            'text': '2 ta HP 880', 'base_product': self.hp.id,
            'client': self.mijoz.id, 'quantity': 2,
        }, format='json')
        request_obj = ConfigurationRequest.objects.get(pk=response.data['id'])

        response = self.client.post(
            f'/api/configuration-requests/{request_obj.id}/lines/',
            {'kind': 'model', 'base_product': self.dell.id, 'quantity': 3},
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIsNone(response.data['configuration'])

    def test_add_line_makes_single_model_request_a_deal(self):
        """B5 (g): bitta modelli ZVKga model qo'shilsa — `deal` paydo bo'ladi."""
        request_obj = self._take(self._single_model_request())
        primary = request_obj.configuration

        response = self.client.get(f'/api/configurations/{primary.id}/')
        self.assertIsNone(response.data['deal'])

        self.client.force_authenticate(self.sales)
        response = self.client.post(
            f'/api/configuration-requests/{request_obj.id}/lines/',
            {'kind': 'model', 'base_product': self.dell.id, 'quantity': 3},
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)

        response = self.client.get(f'/api/configurations/{primary.id}/')
        self.assertIsNotNone(response.data['deal'])
        self.assertEqual(len(response.data['deal']['models']), 2)

    def test_add_line_blocked_when_contract_sent_to_bugalter(self):
        """B3: shartnoma `pending_bugalter` → savdoga yangi model qo'shish 400."""
        request_obj = self._take(self._single_model_request())
        primary = request_obj.configuration

        self.client.force_authenticate(self.engineer)
        self.client.post(f'/api/configurations/{primary.id}/submit/')
        self.client.force_authenticate(self.sales)
        self.client.post(f'/api/configurations/{primary.id}/approve/')
        contract = Contract.objects.get()
        Contract.objects.filter(pk=contract.pk).update(status=Contract.Status.PENDING_BUGALTER)

        response = self.client.post(
            f'/api/configuration-requests/{request_obj.id}/lines/',
            {'kind': 'model', 'base_product': self.dell.id, 'quantity': 3},
            format='json',
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(int(response.data['contract']), contract.id)

    # ------------------------------------------------------------------ B5

    def test_detach_primary_promotes_next_model(self):
        """B5 (c): asosiy model detach qilinadi → boshqasi asosiy bo'ladi, ZVK tirik."""
        request_obj = self._take(self._dual_model_request())
        primary = request_obj.configuration
        dell_config = request_obj.lines.get(base_product=self.dell).configuration

        self.client.force_authenticate(self.sales)
        response = self.client.post(
            f'/api/configurations/{primary.id}/detach/',
            {'reason': 'Mijoz HP dan voz kechdi', 'target': 'cancel'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['promoted_primary'], dell_config.number)

        request_obj.refresh_from_db()
        self.assertEqual(request_obj.configuration_id, dell_config.id)
        self.assertNotIn(request_obj.status, (
            ConfigurationRequest.Status.CANCELLED, ConfigurationRequest.Status.ARCHIVED,
        ))
        # QOLGAN-ISHLAR-2 §5: chiqarilgan (eski asosiy) model YETIM
        # qolmasin — ko'tarilgan qator endi ESKI asosiyga (HP) ishora
        # qiladi, o'chirilmaydi (savdo tarixida ikkalasi ham qoladi)
        self.assertEqual(request_obj.lines.filter(base_product=self.dell).count(), 0)
        orphan_line = request_obj.lines.get(base_product=self.hp)
        self.assertEqual(orphan_line.configuration_id, primary.id)

    def test_detach_last_alive_model_blocked(self):
        """B5 (c) chegara: yagona tirik model qolganda detach 400 — `cancel` kerak."""
        request_obj = self._take(self._dual_model_request())
        primary = request_obj.configuration
        dell_config = request_obj.lines.get(base_product=self.dell).configuration

        self.client.force_authenticate(self.sales)
        self.client.post(
            f'/api/configurations/{dell_config.id}/detach/',
            {'reason': 'Dell kerak emas', 'target': 'cancel'}, format='json',
        )
        response = self.client.post(
            f'/api/configurations/{primary.id}/detach/',
            {'reason': 'HP ham kerak emas', 'target': 'cancel'}, format='json',
        )
        self.assertEqual(response.status_code, 400, response.data)

    def test_detach_assembled_model_warns_variant_stays(self):
        """B5 (b): yig'ilgan model detach → `warnings`da variant aytiladi."""
        request_obj = self._take(self._dual_model_request())
        primary = request_obj.configuration
        dell_config = request_obj.lines.get(base_product=self.dell).configuration

        self.client.force_authenticate(self.engineer)
        self.client.post(f'/api/configuration-requests/{request_obj.id}/submit/')
        self.client.force_authenticate(self.sales)
        self.client.post(f'/api/configuration-requests/{request_obj.id}/approve/')
        contract = Contract.objects.get()
        self._pay(contract)
        apply_movement(
            product=self.dell_ram, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('10'),
        )

        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configurations/{dell_config.id}/assemble/')
        self.assertEqual(response.status_code, 200, response.data)
        dell_config.refresh_from_db()
        self.assertTrue(dell_config.assembled_at)
        self.assertTrue(dell_config.variant_id)
        variant_sku = dell_config.variant.sku

        # Shartnoma qaytarilgan/tuzatilgan deb faraz qilamiz (admin
        # aralashuvi — "eski yozuv" andozasi, 14/15-to'plamlarda ham
        # ishlatilgan): detach qulfi faqat shartnoma DRAFT bo'lganda ochiq,
        # yig'ilgan bo'lishning o'zi buni bloklamaydi — ombor holati qoladi.
        Contract.objects.filter(pk=contract.pk).update(status=Contract.Status.DRAFT)

        self.client.force_authenticate(self.sales)
        response = self.client.post(
            f'/api/configurations/{dell_config.id}/detach/',
            {'reason': "Mijoz Dell'dan voz kechdi", 'target': 'cancel'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(any(variant_sku in w for w in response.data['warnings']))

    # ------------------------------------------------------------ B5 (a) TLD

    def _low_stock_dual_deal(self):
        """Dell (RAM) uchun setUp'da hech qachon kirim qilinmagan — doim
        yetishmaydi; HP (SSD, 50 dona) esa doim yetarli. TLD faqat Dell
        uchun ochiladi, HP'niki tegilmaydi."""
        request_obj = self._take(self._dual_model_request())
        primary = request_obj.configuration
        dell_config = request_obj.lines.get(base_product=self.dell).configuration

        self.client.force_authenticate(self.engineer)
        self.client.post(f'/api/configuration-requests/{request_obj.id}/submit/')
        self.client.force_authenticate(self.sales)
        self.client.post(f'/api/configuration-requests/{request_obj.id}/approve/')
        contract = Contract.objects.get()
        self._pay(contract)
        return request_obj, primary, dell_config, contract

    def test_detach_removes_draft_tld_lines(self):
        """B5 (a): TLD `draft`da — chiqarilgan model qatorlari o'chadi."""
        from apps.procurement.models import ReplenishmentItem

        request_obj, primary, dell_config, contract = self._low_stock_dual_deal()

        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configurations/{primary.id}/request-procurement/')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(ReplenishmentItem.objects.filter(configuration=dell_config).exists())

        # Admin aralashuvi (14/15-to'plamdagi kabi "eski yozuv" andozasi) —
        # detach qulfi shartnoma DRAFT bo'lishini talab qiladi
        Contract.objects.filter(pk=contract.pk).update(status=Contract.Status.DRAFT)

        self.client.force_authenticate(self.sales)
        response = self.client.post(
            f'/api/configurations/{dell_config.id}/detach/',
            {'reason': "Mijoz Dell'dan voz kechdi", 'target': 'cancel'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data['warnings'])
        self.assertFalse(ReplenishmentItem.objects.filter(configuration=dell_config).exists())

    def test_detach_keeps_pending_admin_tld_lines_with_warning(self):
        """B5 (a): TLD `pending_admin`da — qatorlar QOLADI, `warnings`da aytiladi."""
        from apps.procurement.models import Replenishment, ReplenishmentItem

        request_obj, primary, dell_config, contract = self._low_stock_dual_deal()

        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configurations/{primary.id}/request-procurement/')
        self.assertEqual(response.status_code, 201, response.data)
        Replenishment.objects.filter(pk=response.data['id']).update(
            status=Replenishment.Status.PENDING_ADMIN,
        )
        Contract.objects.filter(pk=contract.pk).update(status=Contract.Status.DRAFT)

        self.client.force_authenticate(self.sales)
        response = self.client.post(
            f'/api/configurations/{dell_config.id}/detach/',
            {'reason': "Mijoz Dell'dan voz kechdi", 'target': 'cancel'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['warnings'])
        self.assertTrue(ReplenishmentItem.objects.filter(configuration=dell_config).exists())
