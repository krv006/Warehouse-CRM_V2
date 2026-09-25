from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.configurator.models import Configuration, ConfigurationRequest
from apps.inventory.models import (
    Product,
    ProductSpec,
    StockMovement,
    Warehouse,
)
from apps.inventory.services import apply_movement
from apps.sales.models import Contract, ContractDocument


class RoadmapTests(APITestCase):
    """B8: zanjir ko'zgusi — bitta javob, hamma rol ko'radi, pul yo'q."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.admin = User.objects.create_user('adm', password='p', role=User.Role.ADMIN)
        self.supplier = User.objects.create_user('buy', password='p', role=User.Role.SUPPLIER)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.base = Product.objects.create(
            sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE,
            sale_price=Decimal('12000000'),
        )
        self.ram = Product.objects.create(
            sku='RAM-16', name='RAM 16', kind=Product.Kind.COMPONENT,
            sale_price=Decimal('700000'),
        )
        ProductSpec.objects.create(
            product=self.base, component=self.ram, label='RAM', quantity=1,
        )
        apply_movement(
            product=self.ram, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('10'),
        )

    def _to_waiting_payment(self):
        """ZVK -> ... -> bugalter/admin -> Didox: pul kutilmoqda (12-§1)."""
        self.client.force_authenticate(self.sales)
        request_id = self.client.post('/api/configuration-requests/', {
            'text': '2 ta HP 880', 'base_product': self.base.id,
            'client': self.mijoz.id, 'quantity': 2,
        }, format='json').data['id']
        self.client.force_authenticate(self.engineer)
        take = self.client.post(f'/api/configuration-requests/{request_id}/take/')
        configuration = Configuration.objects.get(pk=take.data['configuration'])
        self.client.post(f'/api/configurations/{configuration.id}/submit/')
        self.client.force_authenticate(self.sales)
        self.client.post(f'/api/configurations/{configuration.id}/approve/')
        configuration.refresh_from_db()
        contract = configuration.active_contract
        ContractDocument.objects.update_or_create(contract=contract, defaults={'body': '<p>x</p>'})
        self.client.post(f'/api/contracts/{contract.id}/submit/')
        # 12-§1: sales -> bugalter -> admin -> Didox -> to'lov
        self.client.force_authenticate(self.bugalter)
        self.client.post(f'/api/contracts/{contract.id}/approve/')
        contract.refresh_from_db()
        if contract.status == Contract.Status.PENDING_ADMIN:
            self.client.force_authenticate(self.admin)
            self.client.post(f'/api/contracts/{contract.id}/approve/')
            self.client.force_authenticate(self.bugalter)
        self.client.post(
            f'/api/contracts/{contract.id}/send-didox/',
            {'didox_number': 'DDX-1'}, format='json',
        )
        self.client.post(f'/api/contracts/{contract.id}/confirm-didox/')
        return (
            ConfigurationRequest.objects.get(pk=request_id), configuration, contract,
        )

    def test_same_roadmap_from_three_entries_for_all_roles(self):
        """Uch kirish nuqtasi — bitta roadmap; bugalter/buyurtmachi ham ko'radi."""
        request_obj, configuration, contract = self._to_waiting_payment()
        urls = [
            f'/api/configuration-requests/{request_obj.id}/roadmap/',
            f'/api/configurations/{configuration.id}/roadmap/',
            f'/api/contracts/{contract.id}/roadmap/',
        ]
        for user in (self.bugalter, self.supplier, self.engineer, self.sales):
            self.client.force_authenticate(user)
            for url in urls:
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200, (user.username, url))
                self.assertEqual(response.data['request']['number'], request_obj.number)
                self.assertEqual(response.data['current_key'], 'prepayment')

    def test_full_steps_with_states(self):
        request_obj, configuration, contract = self._to_waiting_payment()
        self.client.force_authenticate(self.admin)
        response = self.client.get(
            f'/api/configuration-requests/{request_obj.id}/roadmap/',
        )
        steps = {s['key']: s for s in response.data['steps']}
        # 20-§3.5: `finalize` bilan `ship` orasiga `act_review` qo'shildi
        self.assertEqual(len(response.data['steps']), 20)

        self.assertEqual(steps['zvk_created']['state'], 'done')
        self.assertEqual(steps['sales_review']['state'], 'done')
        self.assertEqual(steps['sales_review']['actor']['full_name'], 'sal')
        self.assertEqual(steps['didox_sent']['state'], 'done')
        self.assertEqual(steps['prepayment']['state'], 'current')
        # 13–16 to'lovgacha qulf (B4) — blocked, kelajakda ism yo'q
        self.assertEqual(steps['assemble']['state'], 'blocked')
        self.assertIsNone(steps['assemble']['actor']['full_name'])
        self.assertEqual(steps['assemble']['actor']['role'], 'engineer')
        self.assertEqual(steps['ship']['state'], 'pending')
        # Hujjat raqami hammaga, kirish esa can_open bilan
        self.assertEqual(
            steps['prepayment']['document']['number'], contract.number,
        )

    def test_finalize_sla_counts_from_assembled_not_cfg_approval(self):
        """QOLGAN-ISHLAR #3: qadam HAQIQATAN boshlangan paytdan sanaladi —
        CFG `approved` bo'lib turgan (o'zgarmagan) paytdan emas (CFG-00052)."""
        from datetime import timedelta

        from django.utils.timezone import now

        request_obj, configuration, contract = self._to_waiting_payment()
        self.client.force_authenticate(self.bugalter)
        self.client.post(f'/api/contracts/{contract.id}/confirm-payment/', {
            'amount': str(contract.total_amount),
        }, format='json')

        # CFG ancha oldin approved bo'lgan — eski kod shu paytdan sanardi
        Configuration.objects.filter(pk=configuration.pk).update(
            status_changed_at=now() - timedelta(days=10),
        )

        # Yig'ish esa HOZIRGINA sodir bo'ladi
        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configurations/{configuration.id}/assemble/')
        self.assertEqual(response.status_code, 200, response.data)

        response = self.client.get(
            f'/api/configurations/{configuration.id}/roadmap/',
        )
        steps = {s['key']: s for s in response.data['steps']}
        self.assertEqual(steps['finalize']['state'], 'current')
        # Yig'ilgan hozirgina — 10 kun oldingi CFG holatidan emas, danger emas
        self.assertEqual(steps['finalize']['tone'], 'warning')
        self.assertIsNone(steps['finalize']['waiting_days'])

    def test_roadmap_returns_no_money(self):
        """Qat'iy chegara: summa, narx, qoldiq — javobda umuman yo'q."""
        request_obj, configuration, contract = self._to_waiting_payment()
        self.client.force_authenticate(self.supplier)
        response = self.client.get(
            f'/api/contracts/{contract.id}/roadmap/',
        )
        raw = str(response.data)
        for token in ('total_amount', 'prepayment_amount', 'unit_price', 'balance'):
            self.assertNotIn(token, raw)

    def test_can_open_matrix(self):
        """§3.13: kirishni backend aytadi — front taxmin qilmaydi."""
        request_obj, configuration, contract = self._to_waiting_payment()
        self.client.force_authenticate(self.bugalter)
        steps = {
            s['key']: s for s in self.client.get(
                f'/api/contracts/{contract.id}/roadmap/',
            ).data['steps']
        }
        self.assertTrue(steps['prepayment']['can_open'])       # shartnoma — bugalterda
        self.assertFalse(steps['sales_review']['can_open'])     # CFG — bugalterga yopiq

        self.client.force_authenticate(self.engineer)
        steps = {
            s['key']: s for s in self.client.get(
                f'/api/contracts/{contract.id}/roadmap/',
            ).data['steps']
        }
        self.assertTrue(steps['sales_review']['can_open'])      # CFG — engineerda
        self.assertFalse(steps['prepayment']['can_open'])       # SHT — engineerga yopiq

    def test_taken_step_has_document_link_before_it_is_taken(self):
        """QOLGAN-ISHLAR #6: yangi (hali olinmagan) zayavkada ham `taken`
        qadamining hujjati bo'lishi kerak — "Ishga olish" shu sahifada."""
        self.client.force_authenticate(self.sales)
        request_id = self.client.post('/api/configuration-requests/', {
            'text': '2 ta HP 880', 'base_product': self.base.id,
            'client': self.mijoz.id, 'quantity': 2,
        }, format='json').data['id']

        self.client.force_authenticate(self.engineer)
        response = self.client.get(
            f'/api/configuration-requests/{request_id}/roadmap/',
        )
        steps = {s['key']: s for s in response.data['steps']}
        self.assertEqual(steps['taken']['state'], 'current')
        self.assertIsNotNone(steps['taken']['document'])
        self.assertEqual(steps['taken']['document']['type'], 'request')

    def test_rejection_counts_as_repeats(self):
        """§2.1 aylanmasi ro'yxatni cho'zmaydi — repeats bilan ko'rinadi."""
        self.client.force_authenticate(self.sales)
        request_id = self.client.post('/api/configuration-requests/', {
            'text': 'HP 880', 'base_product': self.base.id,
            'client': self.mijoz.id, 'quantity': 1,
        }, format='json').data['id']
        self.client.force_authenticate(self.engineer)
        take = self.client.post(f'/api/configuration-requests/{request_id}/take/')
        configuration_id = take.data['configuration']
        self.client.post(f'/api/configurations/{configuration_id}/submit/')
        self.client.force_authenticate(self.sales)
        self.client.post(
            f'/api/configurations/{configuration_id}/reject/',
            {'comment': 'Mijozga yoqmadi'}, format='json',
        )
        self.client.force_authenticate(self.engineer)
        self.client.post(f'/api/configurations/{configuration_id}/submit/')
        self.client.force_authenticate(self.sales)
        self.client.post(f'/api/configurations/{configuration_id}/approve/')

        response = self.client.get(
            f'/api/configuration-requests/{request_id}/roadmap/',
        )
        steps = {s['key']: s for s in response.data['steps']}
        self.assertEqual(steps['sales_review']['repeats'], 1)
        self.assertEqual(steps['sales_review']['state'], 'done')

    def _draft_chain(self):
        """ZVK -> take: chernovik, hamma qator narxli."""
        self.client.force_authenticate(self.sales)
        request_id = self.client.post('/api/configuration-requests/', {
            'text': 'HP 880', 'base_product': self.base.id,
            'client': self.mijoz.id, 'quantity': 2,
        }, format='json').data['id']
        self.client.force_authenticate(self.engineer)
        take = self.client.post(f'/api/configuration-requests/{request_id}/take/')
        return request_id, Configuration.objects.get(pk=take.data['configuration'])

    def test_draft_current_is_submitted_not_price(self):
        """6-to'plam §1: narx so'ralmagan chernovikda joriy qadam — submitted."""
        request_id, configuration = self._draft_chain()
        response = self.client.get(
            f'/api/configuration-requests/{request_id}/roadmap/',
        )
        self.assertEqual(response.data['current_key'], 'submitted')
        steps = {s['key']: s for s in response.data['steps']}
        # Narxsiz qator yo'q — qadam bu zanjirda ANIQ bo'lmaydi (§2)
        self.assertEqual(steps['price_request']['state'], 'skipped')
        self.assertTrue(steps['price_request']['optional'])
        # §3: current_key doim javobdagi qadamlardan biri
        self.assertIn(response.data['current_key'], steps)

    def test_price_step_pending_then_current_when_asked(self):
        """§2: narxsiz qator bor — pending (xira); so'ralgach — current."""
        request_id, configuration = self._draft_chain()
        no_price = Product.objects.create(
            sku='CBL-X', name='Kabel X', kind=Product.Kind.COMPONENT,
        )
        from apps.configurator.models import ConfigurationItem

        ConfigurationItem.objects.create(
            configuration=configuration, component=no_price, label='K', quantity=1,
        )
        response = self.client.get(
            f'/api/configuration-requests/{request_id}/roadmap/',
        )
        steps = {s['key']: s for s in response.data['steps']}
        self.assertEqual(steps['price_request']['state'], 'pending')
        self.assertEqual(response.data['current_key'], 'submitted')

        self.client.post(f'/api/configurations/{configuration.id}/request-prices/')
        response = self.client.get(
            f'/api/configuration-requests/{request_id}/roadmap/',
        )
        self.assertEqual(response.data['current_key'], 'price_request')
        steps = {s['key']: s for s in response.data['steps']}
        self.assertEqual(steps['price_request']['state'], 'current')

    def test_procurement_steps_follow_missing(self):
        """§2: yetishmovchilik yo'q — skipped; TLD ochiq — chain current."""
        request_obj, configuration, contract = self._to_waiting_payment()
        self.client.force_authenticate(self.admin)
        response = self.client.get(
            f'/api/configurations/{configuration.id}/roadmap/',
        )
        steps = {s['key']: s for s in response.data['steps']}
        # RAM omborda yetarli — ta'minot qadamlari aniq bo'lmaydi
        self.assertEqual(steps['procurement_sent']['state'], 'skipped')
        self.assertEqual(steps['procurement_chain']['state'], 'skipped')

        # Pul keldi, TLD ochildi — ish haqiqatan buyurtmachida
        Contract.objects.filter(pk=contract.pk).update(
            status=Contract.Status.ACTIVE,
        )
        from apps.procurement.models import Replenishment

        Replenishment.objects.create(
            warehouse=self.warehouse, configuration=configuration,
            status=Replenishment.Status.PENDING_BUGALTER, created_by=self.engineer,
        )
        response = self.client.get(
            f'/api/configurations/{configuration.id}/roadmap/',
        )
        self.assertEqual(response.data['current_key'], 'procurement_chain')
        steps = {s['key']: s for s in response.data['steps']}
        self.assertEqual(steps['procurement_sent']['state'], 'done')
        self.assertEqual(steps['procurement_chain']['state'], 'current')

    def test_admin_step_skipped_early_below_threshold(self):
        """§2: summa ma'lum bo'lishi bilan admin qadami taqdiri ham ma'lum."""
        from apps.core.models import CompanyProfile

        profile = CompanyProfile.load()
        profile.admin_approval_threshold = Decimal('999999999999')
        profile.save()
        request_id, configuration = self._draft_chain()
        self.client.post(f'/api/configurations/{configuration.id}/submit/')
        self.client.force_authenticate(self.sales)
        self.client.post(f'/api/configurations/{configuration.id}/approve/')

        response = self.client.get(
            f'/api/configuration-requests/{request_id}/roadmap/',
        )
        steps = {s['key']: s for s in response.data['steps']}
        self.assertEqual(steps['admin_approve']['state'], 'skipped')
        self.assertTrue(steps['admin_approve']['optional'])

    def test_pending_admin_step_is_current(self):
        """10-§3: shartli qadam ustidan sakralmaydi — pending_admin'da joriy u.

        12-§1: admin ruxsati Didoxdan OLDIN — bugalter tasdig'i yetadi.
        """
        request_id, configuration = self._draft_chain()
        self.client.post(f'/api/configurations/{configuration.id}/submit/')
        self.client.force_authenticate(self.sales)
        self.client.post(f'/api/configurations/{configuration.id}/approve/')
        configuration.refresh_from_db()
        contract = configuration.active_contract
        ContractDocument.objects.update_or_create(contract=contract, defaults={'body': '<p>x</p>'})
        self.client.post(f'/api/contracts/{contract.id}/submit/')
        self.client.force_authenticate(self.bugalter)
        self.client.post(f'/api/contracts/{contract.id}/approve/')

        response = self.client.get(
            f'/api/configuration-requests/{request_id}/roadmap/',
        )
        self.assertEqual(response.data['current_key'], 'admin_approve')
        steps = {s['key']: s for s in response.data['steps']}
        self.assertEqual(steps['admin_approve']['state'], 'current')
        self.assertEqual(steps['admin_approve']['actor']['role'], 'admin')

    def test_procurement_sent_current_when_paid_with_missing(self):
        """10-§3: to'lov keldi, yetishmovchilik bor, TLD yo'q — ish engineerda."""
        self.client.force_authenticate(self.sales)
        request_id = self.client.post('/api/configuration-requests/', {
            'text': '20 ta HP 880', 'base_product': self.base.id,
            'client': self.mijoz.id, 'quantity': 20,  # omborda RAM 10 — yetmaydi
        }, format='json').data['id']
        self.client.force_authenticate(self.engineer)
        take = self.client.post(f'/api/configuration-requests/{request_id}/take/')
        configuration = Configuration.objects.get(pk=take.data['configuration'])
        self.client.post(f'/api/configurations/{configuration.id}/submit/')
        self.client.force_authenticate(self.sales)
        self.client.post(f'/api/configurations/{configuration.id}/approve/')
        configuration.refresh_from_db()
        Contract.objects.filter(pk=configuration.active_contract.pk).update(
            status=Contract.Status.ACTIVE,
        )
        self.client.force_authenticate(self.admin)
        response = self.client.get(
            f'/api/configuration-requests/{request_id}/roadmap/',
        )
        self.assertEqual(response.data['current_key'], 'procurement_sent')
        steps = {s['key']: s for s in response.data['steps']}
        self.assertEqual(steps['procurement_sent']['actor']['role'], 'engineer')
        # QOLGAN-ISHLAR #6: TLD hali yo'q — ish CFG sahifasida bajariladi,
        # havola shu yerga (avval `document: None` — kirib bo'lmasdi)
        self.assertEqual(steps['procurement_sent']['document']['type'], 'configuration')
        self.assertEqual(steps['procurement_sent']['document']['number'], configuration.number)

    def test_tld_step_role_and_label_follow_status(self):
        """10-§6: TLD qora quti emas — egasi va nomi holatidan."""
        request_obj, configuration, contract = self._to_waiting_payment()
        Contract.objects.filter(pk=contract.pk).update(
            status=Contract.Status.ACTIVE,
        )
        from apps.procurement.models import Replenishment

        replenishment = Replenishment.objects.create(
            warehouse=self.warehouse, configuration=configuration,
            status=Replenishment.Status.PENDING_BUGALTER, created_by=self.engineer,
        )
        self.client.force_authenticate(self.admin)
        steps = {
            s['key']: s for s in self.client.get(
                f'/api/configurations/{configuration.id}/roadmap/',
            ).data['steps']
        }
        self.assertEqual(steps['procurement_chain']['actor']['role'], 'bugalter')
        self.assertIn('bugalter', steps['procurement_chain']['label'])

        Replenishment.objects.filter(pk=replenishment.pk).update(
            status=Replenishment.Status.ORDERED,
        )
        steps = {
            s['key']: s for s in self.client.get(
                f'/api/configurations/{configuration.id}/roadmap/',
            ).data['steps']
        }
        self.assertEqual(steps['procurement_chain']['actor']['role'], 'buyurtmachi')
        self.assertIn("yo'lda", steps['procurement_chain']['label'])

    def test_cancelled_chain_marks_stop_point(self):
        request_obj, configuration, contract = self._to_waiting_payment()
        self.client.force_authenticate(self.sales)
        self.client.post(
            f'/api/configuration-requests/{request_obj.id}/cancel/',
            {'reason': 'Mijoz voz kechdi'}, format='json',
        )
        response = self.client.get(
            f'/api/configuration-requests/{request_obj.id}/roadmap/',
        )
        steps = {s['key']: s for s in response.data['steps']}
        current = steps[response.data['current_key']]
        self.assertEqual(current['state'], 'cancelled')
        self.assertEqual(current['tone'], 'cancelled')


class MigrateToContractFirstTests(APITestCase):
    """B11: eski `approved` konfiguratsiyalar yangi oqimga ko'chiriladi."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.base = Product.objects.create(
            sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE,
            sale_price=Decimal('12000000'),
        )

    def _approved_config(self, client=None):
        configuration = Configuration.objects.create(
            base_product=self.base, created_by=self.engineer,
            status=Configuration.Status.APPROVED, client=client,
        )
        from apps.configurator.models import ConfigurationItem

        ConfigurationItem.objects.create(
            configuration=configuration, component=self.base,
            label='X', quantity=1, unit_price=Decimal('12000000'),
        )
        return configuration

    def test_creates_contract_for_stuck_configuration(self):
        from io import StringIO

        from django.core.management import call_command

        configuration = self._approved_config(client=self.mijoz)
        orphan = self._approved_config(client=None)

        out = StringIO()
        call_command('migrate_to_contract_first', '--dry-run', stdout=out)
        self.assertFalse(Contract.objects.exists())  # dry-run yozmaydi
        self.assertIn('MIJOZ YO', out.getvalue())

        call_command('migrate_to_contract_first', stdout=StringIO())
        contract = Contract.objects.get()
        self.assertEqual(contract.configuration, configuration)
        self.assertEqual(contract.status, Contract.Status.DRAFT)
        self.assertFalse(orphan.contracts.exists())
