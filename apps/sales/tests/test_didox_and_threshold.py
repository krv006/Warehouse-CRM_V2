from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.core.models import CompanyProfile, Notification
from apps.inventory.models import Product
from apps.sales.models import Contract, ContractApproval


class BaseContractSetup(APITestCase):
    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.admin = User.objects.create_user('adm', password='p', role=User.Role.ADMIN)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.product = Product.objects.create(
            sku='ADS-1', name='adas', sale_price=Decimal('5000000'),
        )
        from apps.inventory.models import StockMovement, Warehouse
        from apps.inventory.services import apply_movement

        apply_movement(
            product=self.product,
            warehouse=Warehouse.objects.create(name='Asosiy ombor'),
            type=StockMovement.Type.IN, quantity=Decimal('10'),
        )

    def _make_pending(self, unit_price='5000000', currency='UZS'):
        self.client.force_authenticate(self.sales)
        contract_id = self.client.post('/api/contracts/', {
            'client': self.mijoz.id,
            'currency': currency,
            'items': [{'product': self.product.id, 'quantity': 1, 'unit_price': unit_price}],
        }, format='json').data['id']
        self.client.post(f'/api/contracts/{contract_id}/submit/')
        return contract_id


class DidoxTests(BaseContractSetup):
    """§11.2: bugalter tasdig'i — "Didoxdan qabul qildim", to'lov ham tarixga tushadi."""

    def test_didox_number_saved_on_bugalter_approve(self):
        contract_id = self._make_pending()
        self.client.force_authenticate(self.bugalter)
        response = self.client.post(f'/api/contracts/{contract_id}/approve/', {
            'didox_number': 'DDX-2026-0091',
            'comment': 'Didoxdan qabul qilib tanishdim',
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)

        contract = Contract.objects.get(pk=contract_id)
        self.assertEqual(contract.didox_number, 'DDX-2026-0091')
        self.assertIsNotNone(contract.didox_accepted_at)
        # Chop etish shakli uchun imzo sanasi ham to'ldi (§10.12.3)
        self.assertIsNotNone(contract.signed_at)

    def test_payment_step_written_to_history(self):
        contract_id = self._make_pending()
        self.client.force_authenticate(self.bugalter)
        self.client.post(f'/api/contracts/{contract_id}/approve/')
        self.client.force_authenticate(self.admin)
        self.client.post(f'/api/contracts/{contract_id}/approve/')

        self.client.force_authenticate(self.bugalter)
        response = self.client.post(f'/api/contracts/{contract_id}/confirm-payment/')
        self.assertEqual(response.status_code, 200, response.data)

        payment_step = ContractApproval.objects.get(
            contract_id=contract_id, step=ContractApproval.Step.PAYMENT,
        )
        self.assertEqual(payment_step.decided_by, self.bugalter)
        self.assertIn("To'lov qabul qilindi", payment_step.comment)


class AdminThresholdTests(BaseContractSetup):
    """§11.3: chegaradan kichik shartnoma admin tasdig'isiz o'tadi."""

    def setUp(self):
        super().setUp()
        profile = CompanyProfile.load()
        profile.admin_approval_threshold = Decimal('10000000')  # 10 mln
        profile.save()

    def test_small_contract_skips_admin(self):
        # 5 mln + QQS = 5.6 mln < 10 mln — admin shart emas
        contract_id = self._make_pending(unit_price='5000000')
        self.client.force_authenticate(self.bugalter)
        response = self.client.post(f'/api/contracts/{contract_id}/approve/')
        self.assertEqual(response.data['status'], Contract.Status.APPROVED)

        # Tarix jim qolmaydi: avtomatik admin yozuvi, decided_by bo'sh
        auto = ContractApproval.objects.get(
            contract_id=contract_id, step=ContractApproval.Step.ADMIN,
        )
        self.assertIsNone(auto.decided_by)
        self.assertIn('chegara', auto.comment)

        # Bildirishnoma yolg'on gapirmaydi — "admin tasdiqladi" deyilmaydi
        note = Notification.objects.filter(
            user=self.bugalter, entity='Contract', title__contains='pul kutilmoqda',
        ).get()
        self.assertNotIn('admin tasdiqladi', note.title)

    def test_big_contract_still_goes_to_admin(self):
        # 10 mln + QQS = 11.2 mln >= 10 mln — adminga boradi
        contract_id = self._make_pending(unit_price='10000000')
        self.client.force_authenticate(self.bugalter)
        response = self.client.post(f'/api/contracts/{contract_id}/approve/')
        self.assertEqual(response.data['status'], Contract.Status.PENDING_ADMIN)

    def test_foreign_currency_always_goes_to_admin(self):
        """Chegara so'mda — boshqa valyuta doim adminga (kurs yo'q)."""
        contract_id = self._make_pending(unit_price='100', currency='USD')
        self.client.force_authenticate(self.bugalter)
        response = self.client.post(f'/api/contracts/{contract_id}/approve/')
        self.assertEqual(response.data['status'], Contract.Status.PENDING_ADMIN)

    def test_zero_threshold_keeps_current_flow(self):
        profile = CompanyProfile.load()
        profile.admin_approval_threshold = Decimal('0')
        profile.save()
        contract_id = self._make_pending(unit_price='100000')
        self.client.force_authenticate(self.bugalter)
        response = self.client.post(f'/api/contracts/{contract_id}/approve/')
        self.assertEqual(response.data['status'], Contract.Status.PENDING_ADMIN)
