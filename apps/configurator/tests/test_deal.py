from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.configurator.models import Configuration, ConfigurationRequest
from apps.inventory.models import Product, ProductSpec, StockMovement, Warehouse
from apps.inventory.services import apply_movement
from apps.sales.models import Contract, ContractDocument


class DealTests(APITestCase):
    """14-to'plam: savdo = bitta ConfigurationRequest — N model + M tovar,
    bitta shartnoma/TLD/ACT. `deal` bloki, avtomatik shartnoma birlashtirish,
    tugamagan savdoni yuborishni bloklash.
    """

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
        ProductSpec.objects.create(product=self.hp, component=self.ssd, label='SSD', quantity=1)
        ProductSpec.objects.create(product=self.dell, component=self.ssd, label='SSD', quantity=1)
        # Qasddan omborda YO'Q — TLD testlari uchun haqiqiy yetishmovchilik
        # kerak; yig'ish kerak bo'lgan testlar assemble'dan oldin o'zi kirim qiladi

    def _single_model_request(self):
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/configuration-requests/', {
            'text': '2 ta HP 880', 'base_product': self.hp.id,
            'client': self.mijoz.id, 'quantity': 2,
        }, format='json')
        return ConfigurationRequest.objects.get(pk=response.data['id'])

    def _mixed_request(self):
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/configuration-requests/', {
            'text': '10 ta HP 880 + 20 ta Dell + 20 ta zapas SSD',
            'base_product': self.hp.id, 'client': self.mijoz.id, 'quantity': 10,
            'lines': [
                {'kind': 'model', 'base_product': self.dell.id, 'quantity': 20, 'text': 'Dell'},
                {'kind': 'item', 'base_product': self.ssd.id, 'quantity': 20, 'text': 'zapas'},
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

    def _submit(self, configuration):
        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configurations/{configuration.id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)

    def _approve(self, configuration, **body):
        self.client.force_authenticate(self.sales)
        response = self.client.post(
            f'/api/configurations/{configuration.id}/approve/', body, format='json',
        )
        return response

    # ---------------------------------------------------------- §10 A/regressiya

    def test_single_model_deal_is_none(self):
        """§10 A: bitta modelli zayavkada `deal` — null, hech narsa o'zgarmaydi."""
        request_obj = self._take(self._single_model_request())
        configuration = request_obj.configuration
        self._submit(configuration)
        response = self._approve(configuration)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(response.data['deal'])
        self.assertEqual(Contract.objects.count(), 1)

    # -------------------------------------------------------------------- §2

    def test_deal_block_shape_for_multi_model(self):
        request_obj = self._take(self._mixed_request())
        primary = request_obj.configuration
        dell_line = request_obj.lines.get(base_product=self.dell)

        response = self.client.get(f'/api/configurations/{primary.id}/')
        deal = response.data['deal']
        self.assertIsNotNone(deal)
        self.assertEqual(deal['request'], request_obj.id)
        self.assertEqual(deal['request_number'], request_obj.number)
        self.assertEqual(len(deal['models']), 2)
        numbers = {m['number'] for m in deal['models']}
        self.assertEqual(numbers, {primary.number, dell_line.configuration.number})
        primary_row = next(m for m in deal['models'] if m['number'] == primary.number)
        self.assertTrue(primary_row['is_primary'])
        self.assertEqual(len(deal['items']), 1)
        self.assertEqual(deal['items'][0]['product'], self.ssd.id)
        self.assertIsNone(deal['contract'])  # hali hech kim tasdiqlamagan

        # Ikkinchi model sahifasidan ham xuddi shu shakl
        response2 = self.client.get(f'/api/configurations/{dell_line.configuration.id}/')
        self.assertEqual(response2.data['deal']['request'], request_obj.id)

        # Zayavka sahifasidan ham xuddi shu shakl
        response3 = self.client.get(f'/api/configuration-requests/{request_obj.id}/')
        self.assertEqual(len(response3.data['deal']['models']), 2)

    # ------------------------------------------------------------------ §3/§10 B

    def test_second_approve_merges_into_existing_draft_without_contract_param(self):
        """§3.3b: `contract` yuborilmasa ham ikkinchi model YANGI shartnoma ochmaydi."""
        request_obj = self._take(self._mixed_request())
        primary = request_obj.configuration
        dell_config = request_obj.lines.get(base_product=self.dell).configuration

        self._submit(primary)
        response = self._approve(primary)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Contract.objects.count(), 1)
        contract = Contract.objects.get()

        self._submit(dell_config)
        response = self._approve(dell_config)  # `contract` YUBORILMAGAN
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Contract.objects.count(), 1, 'ikkinchi model yangi SHT ochmasligi kerak')
        contract.refresh_from_db()
        # HP (asosiy, birinchi approve'da) + SSD (tovar, shu bilan birga
        # avtomatik qo'shilgan) + Dell (ikkinchi approve)
        self.assertEqual(contract.items.count(), 3)

    def test_separate_contract_true_opens_new(self):
        """§3.2: mijoz ataylab alohida shartnoma so'rasa — ochiladi."""
        request_obj = self._take(self._mixed_request())
        primary = request_obj.configuration
        dell_config = request_obj.lines.get(base_product=self.dell).configuration

        self._submit(primary)
        self._approve(primary)
        self.assertEqual(Contract.objects.count(), 1)

        self._submit(dell_config)
        response = self._approve(dell_config, separate_contract=True)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Contract.objects.count(), 2)

    def test_explicit_contract_still_works(self):
        """§3.1: `contract` berilgan — hozirgidek (o'zgarmaydi)."""
        request_obj = self._take(self._mixed_request())
        primary = request_obj.configuration
        dell_config = request_obj.lines.get(base_product=self.dell).configuration

        self._submit(primary)
        self._approve(primary)
        contract = Contract.objects.get()

        self._submit(dell_config)
        response = self._approve(dell_config, contract=contract.id)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Contract.objects.count(), 1)

    def test_merge_blocked_with_helpful_message_when_contract_already_submitted(self):
        """§3 "Chegaraviy holat": §4 bu holatni deyarli oldini oladi — bu yerda
        eski yozuv/admin aralashuvini simulyatsiya qilish uchun shartnoma
        to'g'ridan-to'g'ri (API'dan emas) `pending_bugalter`ga o'tkaziladi."""
        request_obj = self._take(self._mixed_request())
        primary = request_obj.configuration
        dell_config = request_obj.lines.get(base_product=self.dell).configuration

        self._submit(primary)
        self._approve(primary)
        contract = Contract.objects.get()
        Contract.objects.filter(pk=contract.pk).update(
            status=Contract.Status.PENDING_BUGALTER,
        )

        self._submit(dell_config)
        response = self._approve(dell_config)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(int(response.data['contract']), contract.id)
        self.assertEqual(response.data['contract_status'], 'pending_bugalter')

    # ---------------------------------------------------------------------- §4

    def test_submit_blocked_while_a_model_is_pending(self):
        """§4: bitta model tayyor, ikkinchisi hali chernovik — yuborib bo'lmaydi."""
        request_obj = self._take(self._mixed_request())
        primary = request_obj.configuration
        dell_config = request_obj.lines.get(base_product=self.dell).configuration

        self._submit(primary)
        self._approve(primary)
        contract = Contract.objects.get()

        self.client.force_authenticate(self.sales)
        ContractDocument.objects.update_or_create(contract=contract, defaults={'body': '<p>x</p>'})
        response = self.client.post(f'/api/contracts/{contract.id}/submit/')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(response.data['pending_models']), 1)
        # DRF ValidationError ichki qiymatlarni ErrorDetail(str) qiladi
        self.assertEqual(int(response.data['pending_models'][0]['id']), dell_config.id)

        # Ikkinchi model ham tasdiqlangach — endi yuboriladi
        self._submit(dell_config)
        self._approve(dell_config)
        response = self.client.post(f'/api/contracts/{contract.id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)

    # ---------------------------------------------------------------------- §5

    def test_detach_cancel_removes_item_and_recalculates_total(self):
        request_obj = self._take(self._mixed_request())
        primary = request_obj.configuration
        dell_config = request_obj.lines.get(base_product=self.dell).configuration

        self._submit(primary)
        self._approve(primary)
        contract = Contract.objects.get()
        self._submit(dell_config)
        self._approve(dell_config)
        contract.refresh_from_db()
        self.assertEqual(contract.items.count(), 3)  # HP + SSD + Dell
        total_before = contract.total_amount

        self.client.force_authenticate(self.sales)
        response = self.client.post(
            f'/api/configurations/{dell_config.id}/detach/',
            {'reason': "Mijoz Dell'dan voz kechdi", 'target': 'cancel'},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['target'], 'cancel')
        self.assertIsNone(response.data['contract'])

        dell_config.refresh_from_db()
        self.assertEqual(dell_config.status, Configuration.Status.CANCELLED)
        self.assertEqual(dell_config.cancel_reason, "Mijoz Dell'dan voz kechdi")
        contract.refresh_from_db()
        self.assertEqual(contract.items.count(), 2)  # HP + SSD qoladi
        self.assertLess(contract.total_amount, total_before)

    def test_detach_separate_gives_own_contract(self):
        request_obj = self._take(self._mixed_request())
        primary = request_obj.configuration
        dell_config = request_obj.lines.get(base_product=self.dell).configuration

        self._submit(primary)
        self._approve(primary)
        shared_contract = Contract.objects.get()
        self._submit(dell_config)
        self._approve(dell_config)

        self.client.force_authenticate(self.sales)
        response = self.client.post(
            f'/api/configurations/{dell_config.id}/detach/',
            {'reason': 'Mijoz alohida hujjat so\'radi', 'target': 'separate'},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNotNone(response.data['contract'])
        self.assertEqual(Contract.objects.count(), 2)

        dell_config.refresh_from_db()
        self.assertNotEqual(dell_config.status, Configuration.Status.CANCELLED)
        new_contract = dell_config.active_contract
        self.assertNotEqual(new_contract.id, shared_contract.id)
        self.assertEqual(new_contract.items.get().product, self.dell)

    def test_detach_makes_deal_fully_done(self):
        """§5(a)/(b): bekor qilingan model zayavkani abadiy ochiq qoldirmaydi."""
        request_obj = self._take(self._mixed_request())
        primary = request_obj.configuration
        dell_config = request_obj.lines.get(base_product=self.dell).configuration

        self._submit(primary)
        self._approve(primary)
        contract = Contract.objects.get()

        self.client.force_authenticate(self.sales)
        self.client.post(
            f'/api/configurations/{dell_config.id}/detach/',
            {'reason': 'voz kechdi', 'target': 'cancel'}, format='json',
        )

        request_obj.refresh_from_db()
        self.assertTrue(request_obj.is_fully_done)
        ContractDocument.objects.update_or_create(contract=contract, defaults={'body': '<p>x</p>'})
        response = self.client.post(f'/api/contracts/{contract.id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)

    def test_detach_blocked_when_contract_paid(self):
        request_obj = self._take(self._mixed_request())
        primary = request_obj.configuration
        dell_config = request_obj.lines.get(base_product=self.dell).configuration

        self._submit(primary)
        self._approve(primary)
        contract = Contract.objects.get()
        self._submit(dell_config)
        self._approve(dell_config)
        Contract.objects.filter(pk=contract.pk).update(status=Contract.Status.ACTIVE)

        self.client.force_authenticate(self.sales)
        response = self.client.post(
            f'/api/configurations/{dell_config.id}/detach/',
            {'reason': 'voz kechdi', 'target': 'cancel'}, format='json',
        )
        self.assertEqual(response.status_code, 400)

    # ---------------------------------------------------------------------- §8

    def test_roadmap_submitted_step_waits_for_all_models(self):
        """§8: qadam savdo darajasida — bitta model yuborilgani yetmaydi."""
        request_obj = self._take(self._mixed_request())
        primary = request_obj.configuration
        dell_config = request_obj.lines.get(base_product=self.dell).configuration

        self._submit(primary)  # faqat asosiysi yuborildi, Dell hali chernovik

        self.client.force_authenticate(self.admin)
        response = self.client.get(
            f'/api/configuration-requests/{request_obj.id}/roadmap/',
        )
        steps = {s['key']: s for s in response.data['steps']}
        self.assertFalse(steps['submitted']['state'] == 'done')
        self.assertEqual(steps['submitted']['models'], {
            'done': 1, 'total': 2,
            'pending': [{'id': dell_config.id, 'number': dell_config.number}],
        })
        # Havola orqada qolgan (Dell) modelga ishora qiladi
        self.assertEqual(steps['submitted']['document']['number'], dell_config.number)

        # Ikkinchisi ham yuborilgach — endi tayyor, `models` to'liq
        self._submit(dell_config)
        response = self.client.get(
            f'/api/configuration-requests/{request_obj.id}/roadmap/',
        )
        steps = {s['key']: s for s in response.data['steps']}
        self.assertEqual(steps['submitted']['models']['done'], 2)
        self.assertEqual(steps['submitted']['models']['pending'], [])

    def test_roadmap_models_null_for_single_model_chain(self):
        """§8.2: bitta modelli savdoda `models` — null."""
        request_obj = self._take(self._single_model_request())
        self._submit(request_obj.configuration)
        self.client.force_authenticate(self.admin)
        response = self.client.get(
            f'/api/configuration-requests/{request_obj.id}/roadmap/',
        )
        steps = {s['key']: s for s in response.data['steps']}
        self.assertIsNone(steps['submitted']['models'])
        self.assertIsNone(steps['sales_review']['models'])

    def test_stuck_second_model_shows_up_in_roadmap_list(self):
        """§8/§10 I: ikkinchi modelda ish turib qolgan bo'lsa bosh sahifada ko'rinadi."""
        request_obj = self._take(self._mixed_request())
        primary = request_obj.configuration
        dell_config = request_obj.lines.get(base_product=self.dell).configuration
        self._submit(primary)
        self._approve(primary)
        # Dell hali `submit` qilinmagan — ish engineerda turib qolgan

        self.client.force_authenticate(self.engineer)
        response = self.client.get('/api/roadmaps/?state=open')
        numbers = [row['request']['number'] for row in response.data['results']]
        self.assertIn(request_obj.number, numbers)
        row = next(r for r in response.data['results'] if r['request']['number'] == request_obj.number)
        steps = {s['key']: s for s in row['steps']}
        self.assertEqual(steps['submitted']['document']['number'], dell_config.number)

    # ---------------------------------------------------------------------- §6

    def _pay(self, contract):
        from apps.sales.services import (
            approve_contract, confirm_didox, confirm_payment, send_didox,
        )

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

    def test_second_model_missing_joins_same_tld(self):
        """§6 (1)/(2): ikki modelli savdo — bitta TLD, qatorlarda `configuration` to'lgan."""
        request_obj = self._take(self._mixed_request())
        primary = request_obj.configuration  # HP, 10 ta — SSD 10 dona kerak
        dell_config = request_obj.lines.get(base_product=self.dell).configuration  # 20 ta

        self._submit(primary)
        self._approve(primary)
        contract = Contract.objects.get()
        self._submit(dell_config)
        self._approve(dell_config)
        self._pay(contract)

        primary.refresh_from_db()
        dell_config.refresh_from_db()
        self.assertEqual(primary.status, Configuration.Status.APPROVED)
        self.assertEqual(dell_config.status, Configuration.Status.APPROVED)

        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configurations/{primary.id}/request-procurement/')
        self.assertEqual(response.status_code, 201, response.data)
        replenishment_id = response.data['id']

        response2 = self.client.post(f'/api/configurations/{dell_config.id}/request-procurement/')
        self.assertEqual(response2.status_code, 201, response2.data)
        self.assertEqual(response2.data['id'], replenishment_id, "ikkinchi model YANGI TLD ochmasligi kerak")

        from apps.procurement.models import Replenishment

        self.assertEqual(Replenishment.objects.count(), 1)
        replenishment = Replenishment.objects.get(pk=replenishment_id)
        configs_on_items = set(replenishment.items.values_list('configuration_id', flat=True))
        self.assertEqual(configs_on_items, {primary.id, dell_config.id})

    def test_tld_pending_admin_allows_new_tld(self):
        """§6.5: TLD `pending_admin`da — yangi qo'shib bo'lmaydi, YANGI TLD ochishga ruxsat."""
        request_obj = self._take(self._mixed_request())
        primary = request_obj.configuration
        dell_config = request_obj.lines.get(base_product=self.dell).configuration

        self._submit(primary)
        self._approve(primary)
        contract = Contract.objects.get()
        self._submit(dell_config)
        self._approve(dell_config)
        self._pay(contract)

        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configurations/{primary.id}/request-procurement/')
        self.assertEqual(response.status_code, 201, response.data)
        from apps.procurement.models import Replenishment

        Replenishment.objects.filter(pk=response.data['id']).update(
            status=Replenishment.Status.PENDING_ADMIN,
        )

        response2 = self.client.post(f'/api/configurations/{dell_config.id}/request-procurement/')
        self.assertEqual(response2.status_code, 201, response2.data)
        self.assertNotEqual(response2.data['id'], response.data['id'])
        self.assertEqual(Replenishment.objects.count(), 2)

    def test_single_model_tld_unaffected(self):
        """§6 regressiya: bitta modelli savdoda TLD javobida `configuration` null, xulq eski."""
        request_obj = self._take(self._single_model_request())
        configuration = request_obj.configuration
        self._submit(configuration)
        self._approve(configuration)
        contract = Contract.objects.get()
        self._pay(contract)

        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configurations/{configuration.id}/request-procurement/')
        self.assertEqual(response.status_code, 201, response.data)
        item = response.data['items'][0]
        self.assertIsNone(item['configuration'])

    # ---------------------------------------------------------------------- §7

    def test_finalize_reuses_sibling_act(self):
        """§7 (1): ikkinchi model finalize'da ACT ni qayta tanlamaydi."""
        from datetime import date

        from apps.configurator.models import Act
        from apps.inventory.models import StockMovement
        from apps.inventory.services import apply_movement

        request_obj = self._take(self._mixed_request())
        primary = request_obj.configuration
        dell_config = request_obj.lines.get(base_product=self.dell).configuration

        self._submit(primary)
        self._approve(primary)
        contract = Contract.objects.get()
        self._submit(dell_config)
        self._approve(dell_config)
        self._pay(contract)

        apply_movement(
            product=self.ssd, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('50'),
        )
        act = Act.objects.create(number='ACT-0001', title='ACT', issued_at=date.today())

        self.client.force_authenticate(self.engineer)
        self.client.post(f'/api/configurations/{primary.id}/assemble/')
        response = self.client.post(
            f'/api/configurations/{primary.id}/finalize/', {'act': act.id}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)

        self.client.post(f'/api/configurations/{dell_config.id}/assemble/')
        response2 = self.client.post(f'/api/configurations/{dell_config.id}/finalize/')
        self.assertEqual(response2.status_code, 200, response2.data)
        dell_config.refresh_from_db()
        self.assertEqual(dell_config.act_id, act.id)

    def test_deal_act_suggestion_covers_only_assembled_models(self):
        from apps.inventory.models import StockMovement
        from apps.inventory.services import apply_movement

        request_obj = self._take(self._mixed_request())
        primary = request_obj.configuration
        dell_config = request_obj.lines.get(base_product=self.dell).configuration
        self._submit(primary)
        self._approve(primary)
        contract = Contract.objects.get()
        self._submit(dell_config)
        self._approve(dell_config)
        self._pay(contract)

        apply_movement(
            product=self.ssd, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('50'),
        )
        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configurations/{primary.id}/assemble/')
        self.assertEqual(response.status_code, 200, response.data)

        response = self.client.get(
            f'/api/configuration-requests/{request_obj.id}/act-suggestion/',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn(self.hp.name, response.data['act_suggestion'])
        self.assertNotIn(self.dell.name, response.data['act_suggestion'])

    def test_submit_single_model_unaffected(self):
        """§4 regressiya: bitta modelli savdoda tekshiruv sezilmaydi."""
        request_obj = self._take(self._single_model_request())
        configuration = request_obj.configuration
        self._submit(configuration)
        self._approve(configuration)
        contract = Contract.objects.get()
        self.client.force_authenticate(self.sales)
        ContractDocument.objects.update_or_create(contract=contract, defaults={'body': '<p>x</p>'})
        response = self.client.post(f'/api/contracts/{contract.id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)
