from datetime import date
from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.configurator.models import Act, ConfigurationRequest
from apps.core.models import CompanyProfile, Notification
from apps.inventory.models import Product, ProductSpec, StockMovement, Warehouse
from apps.inventory.services import apply_movement
from apps.sales.models import Contract, ContractDocument


class ActApprovalTests(APITestCase):
    """20-§3: ACT bugalter tasdig'idan o'tmaguncha mol ombordan chiqmasin."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
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
        self.part = Product.objects.create(
            sku='NVME-1', name='Samsung NVMe', kind=Product.Kind.COMPONENT,
            sale_price=Decimal('900000'),
        )
        ProductSpec.objects.create(product=self.hp, component=self.part, label='NVMe', quantity=1)
        ProductSpec.objects.create(product=self.dell, component=self.part, label='NVMe', quantity=1)
        apply_movement(
            product=self.part, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('50'),
        )
        profile = CompanyProfile.load()
        profile.admin_approval_threshold = Decimal('0')
        profile.save()

    def _pay(self, contract):
        from apps.sales.services import approve_contract, confirm_didox, confirm_payment, send_didox

        self.client.force_authenticate(self.sales)
        ContractDocument.objects.update_or_create(contract=contract, defaults={'body': '<p>x</p>'})
        response = self.client.post(f'/api/contracts/{contract.id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)
        contract.refresh_from_db()
        approve_contract(contract, self.bugalter)
        contract.refresh_from_db()
        if contract.status == Contract.Status.PENDING_ADMIN:
            approve_contract(contract, self.admin)
            contract.refresh_from_db()
        send_didox(contract, self.admin, 'DDX-1')
        confirm_didox(contract, self.admin)
        contract.refresh_from_db()
        confirm_payment(contract, self.admin, amount=contract.total_amount)
        contract.refresh_from_db()

    def _single_assembled_configuration(self):
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/configuration-requests/', {
            'text': '1 ta HP 880', 'base_product': self.hp.id,
            'client': self.mijoz.id, 'quantity': 1,
        }, format='json')
        request_obj = ConfigurationRequest.objects.get(pk=response.data['id'])
        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configuration-requests/{request_obj.id}/take/')
        request_obj.refresh_from_db()
        configuration = request_obj.configuration

        response = self.client.post(f'/api/configurations/{configuration.id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)
        self.client.force_authenticate(self.sales)
        response = self.client.post(f'/api/configurations/{configuration.id}/approve/')
        self.assertEqual(response.status_code, 200, response.data)
        contract = Contract.objects.get()
        self._pay(contract)

        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configurations/{configuration.id}/assemble/')
        self.assertEqual(response.status_code, 200, response.data)
        configuration.refresh_from_db()
        return configuration, contract

    def _dual_assembled_deal(self):
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/configuration-requests/', {
            'text': '1 ta HP + 1 ta Dell', 'base_product': self.hp.id,
            'client': self.mijoz.id, 'quantity': 1,
            'lines': [{'kind': 'model', 'base_product': self.dell.id, 'quantity': 1, 'text': 'Dell'}],
        }, format='json')
        request_obj = ConfigurationRequest.objects.get(pk=response.data['id'])
        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configuration-requests/{request_obj.id}/take/')
        self.assertEqual(response.status_code, 200, response.data)
        request_obj.refresh_from_db()
        primary = request_obj.configuration
        dell_config = request_obj.lines.get(base_product=self.dell).configuration

        response = self.client.post(f'/api/configuration-requests/{request_obj.id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)
        self.client.force_authenticate(self.sales)
        response = self.client.post(f'/api/configuration-requests/{request_obj.id}/approve/')
        self.assertEqual(response.status_code, 200, response.data)
        contract = Contract.objects.get()
        self._pay(contract)

        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configuration-requests/{request_obj.id}/assemble/')
        self.assertEqual(response.status_code, 200, response.data)
        primary.refresh_from_db()
        dell_config.refresh_from_db()
        return request_obj, primary, dell_config, contract

    # -------------------------------------------------------------- finalize

    def test_finalize_sends_act_for_review_single_model(self):
        """20-§3.9: bitta model finalize → ACT `pending_bugalter`, bugalter navbatida 1."""
        configuration, _contract = self._single_assembled_configuration()
        act = Act.objects.create(number='ACT-0001', title='ACT', issued_at=date.today(), created_by=self.engineer)

        response = self.client.post(
            f'/api/configurations/{configuration.id}/finalize/', {'act': act.id}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        act.refresh_from_db()
        self.assertEqual(act.status, Act.Status.PENDING_BUGALTER)

        notes = Notification.objects.filter(user=self.bugalter, title__contains="tasdig'ingizni")
        self.assertTrue(notes.exists())

        self.client.force_authenticate(self.bugalter)
        counts = self.client.get('/api/sidebar-counts/').data
        self.assertEqual(counts['acts'], 1)

    def test_two_model_deal_act_stays_draft_until_last_finalize(self):
        """20-§3.9: 1-model finalize → ACT hali `draft`; 2-model ham → `pending_bugalter`."""
        request_obj, primary, dell_config, _contract = self._dual_assembled_deal()
        act = Act.objects.create(number='ACT-0001', title='ACT', issued_at=date.today(), created_by=self.engineer)

        response = self.client.post(
            f'/api/configurations/{primary.id}/finalize/', {'act': act.id}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        act.refresh_from_db()
        self.assertEqual(act.status, Act.Status.DRAFT)

        response = self.client.post(f'/api/configurations/{dell_config.id}/finalize/')
        self.assertEqual(response.status_code, 200, response.data)
        act.refresh_from_db()
        self.assertEqual(act.status, Act.Status.PENDING_BUGALTER)

    def test_finalize_rejects_foreign_approved_act(self):
        """20-§3.1: begona `approved` ACT finalize'da tanlanmaydi."""
        configuration, _contract = self._single_assembled_configuration()
        foreign_act = Act.objects.create(
            number='ACT-9999', title='Boshqa savdo', issued_at=date.today(),
            status=Act.Status.APPROVED,
        )
        response = self.client.post(
            f'/api/configurations/{configuration.id}/finalize/',
            {'act': foreign_act.id}, format='json',
        )
        self.assertEqual(response.status_code, 400, response.data)

    # ------------------------------------------------------------ amallar

    def test_bugalter_approve_and_reject_cycle(self):
        configuration, _contract = self._single_assembled_configuration()
        act = Act.objects.create(number='ACT-0001', title='ACT', issued_at=date.today(), created_by=self.engineer)
        self.client.post(
            f'/api/configurations/{configuration.id}/finalize/', {'act': act.id}, format='json',
        )
        act.refresh_from_db()
        self.assertEqual(act.status, Act.Status.PENDING_BUGALTER)

        # Engineer tasdiqlay olmaydi
        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/acts/{act.id}/approve/')
        self.assertEqual(response.status_code, 403, response.data)

        # Bugalter izohsiz qaytara olmaydi
        self.client.force_authenticate(self.bugalter)
        response = self.client.post(f'/api/acts/{act.id}/reject/')
        self.assertEqual(response.status_code, 400, response.data)

        # Qaytaradi → engineer tuzatib qayta yuboradi → bugalter tasdiqlaydi
        response = self.client.post(f'/api/acts/{act.id}/reject/', {'comment': 'Sana xato'}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        act.refresh_from_db()
        self.assertEqual(act.status, Act.Status.REJECTED)
        self.assertTrue(
            Notification.objects.filter(user=self.engineer, title__contains='qaytarildi').exists(),
        )

        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/acts/{act.id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)
        act.refresh_from_db()
        self.assertEqual(act.status, Act.Status.PENDING_BUGALTER)

        self.client.force_authenticate(self.bugalter)
        response = self.client.post(f'/api/acts/{act.id}/approve/')
        self.assertEqual(response.status_code, 200, response.data)
        act.refresh_from_db()
        self.assertEqual(act.status, Act.Status.APPROVED)

    # ------------------------------------------------------------- roadmap

    def test_roadmap_has_19_steps_and_act_review_current(self):
        configuration, contract = self._single_assembled_configuration()
        act = Act.objects.create(number='ACT-0001', title='ACT', issued_at=date.today(), created_by=self.engineer)
        self.client.post(
            f'/api/configurations/{configuration.id}/finalize/', {'act': act.id}, format='json',
        )

        self.client.force_authenticate(self.bugalter)
        response = self.client.get(f'/api/contracts/{contract.id}/roadmap/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data['steps']), 20)
        self.assertEqual(response.data['current_key'], 'act_review')
        step = {s['key']: s for s in response.data['steps']}['act_review']
        self.assertEqual(step['actor']['role'], 'bugalter')

    def test_roadmap_act_review_skipped_for_configuration_less_contract(self):
        """20-§3.5: konfiguratsiyasiz shartnomada `act_review` — `skipped`."""
        contract = Contract.objects.create(
            client=self.mijoz, total_amount=Decimal('5000000'),
            created_by=self.sales, status=Contract.Status.ACTIVE,
        )
        from apps.sales.models import ContractItem

        ContractItem.objects.create(
            contract=contract, product=self.hp, quantity=1, unit_price=Decimal('5000000'),
        )
        self.client.force_authenticate(self.sales)
        response = self.client.get(f'/api/contracts/{contract.id}/roadmap/')
        self.assertEqual(response.status_code, 200, response.data)
        step = {s['key']: s for s in response.data['steps']}['act_review']
        self.assertEqual(step['state'], 'skipped')
