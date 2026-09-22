from datetime import timedelta
from decimal import Decimal

from django.utils.timezone import now

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.core.models import CompanyProfile
from apps.inventory.models import Product
from apps.sales.models import Contract, ContractApproval, ContractItem


class DidoxStepsTests(APITestCase):
    """12-§1: sales -> bugalter -> admin -> Didox (ikki qadam) -> to'lov."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.admin = User.objects.create_user('adm', password='p', role=User.Role.ADMIN)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.product = Product.objects.create(sku='HP-880', name='HP 880')

    def _pending_contract(self, total='50000000'):
        contract = Contract.objects.create(
            client=self.mijoz, total_amount=Decimal(total),
            created_by=self.sales, status=Contract.Status.PENDING_BUGALTER,
        )
        ContractItem.objects.create(
            contract=contract, product=self.product, quantity=1,
            unit_price=Decimal(total),
        )
        return contract

    def _ready_for_didox(self, contract):
        """Bugalter va admin tasdig'ini o'tkazib, Didoxga tayyor holatga olib boradi."""
        self.client.force_authenticate(self.bugalter)
        self.client.post(f'/api/contracts/{contract.id}/approve/')
        contract.refresh_from_db()
        if contract.status == Contract.Status.PENDING_ADMIN:
            self.client.force_authenticate(self.admin)
            self.client.post(f'/api/contracts/{contract.id}/approve/')
            contract.refresh_from_db()
        self.client.force_authenticate(self.bugalter)

    def test_admin_approve_before_didox_moves_to_ready(self):
        """12-§1: admin ruxsati endi Didoxdan OLDIN — pending_admin -> ready_for_didox."""
        contract = self._pending_contract()
        self.client.force_authenticate(self.bugalter)
        response = self.client.post(f'/api/contracts/{contract.id}/approve/')
        self.assertEqual(response.status_code, 200, response.data)
        contract.refresh_from_db()
        self.assertEqual(contract.status, Contract.Status.PENDING_ADMIN)

        self.client.force_authenticate(self.admin)
        response = self.client.post(f'/api/contracts/{contract.id}/approve/')
        self.assertEqual(response.status_code, 200, response.data)
        contract.refresh_from_db()
        self.assertEqual(contract.status, Contract.Status.READY_FOR_DIDOX)
        # Didox raqami hali yo'q — u faqat send-didox'da kiritiladi
        self.assertEqual(contract.didox_number, '')

    def test_send_didox_requires_ready_state_and_number(self):
        contract = self._pending_contract()
        self.client.force_authenticate(self.bugalter)
        # Bugalter va admin tasdig'idan oldin Didoxga yuborib bo'lmaydi
        response = self.client.post(
            f'/api/contracts/{contract.id}/send-didox/',
            {'didox_number': 'DDX-77'}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('detail', response.data)

        self._ready_for_didox(contract)
        response = self.client.post(
            f'/api/contracts/{contract.id}/send-didox/', {}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('didox_number', response.data)

        response = self.client.post(
            f'/api/contracts/{contract.id}/send-didox/',
            {'didox_number': 'DDX-77'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        contract.refresh_from_db()
        self.assertEqual(contract.status, Contract.Status.PENDING_DIDOX)
        self.assertEqual(contract.didox_number, 'DDX-77')
        self.assertIsNotNone(contract.didox_sent_at)
        self.assertIsNone(contract.didox_accepted_at)  # hali imzolanmagan
        self.assertTrue(
            ContractApproval.objects.filter(
                contract=contract, step=ContractApproval.Step.DIDOX,
            ).exists(),
        )

    def test_confirm_didox_goes_straight_to_approved(self):
        """12-§1: admin allaqachon oldin tasdiqlagan — Didox tasdiqi to'g'ridan approved beradi."""
        contract = self._pending_contract()
        self._ready_for_didox(contract)
        self.client.post(
            f'/api/contracts/{contract.id}/send-didox/',
            {'didox_number': 'DDX-77'}, format='json',
        )
        response = self.client.post(f'/api/contracts/{contract.id}/confirm-didox/')
        self.assertEqual(response.status_code, 200, response.data)
        contract.refresh_from_db()
        self.assertEqual(contract.status, Contract.Status.APPROVED)
        self.assertIsNotNone(contract.didox_accepted_at)

    def test_small_contract_reaches_didox_without_admin(self):
        """§11.3 chegara mantig'i endi bugalter tasdig'ida ishlaydi, Didoxdan oldin."""
        profile = CompanyProfile.load()
        profile.admin_approval_threshold = Decimal('100000000')
        profile.save()
        contract = self._pending_contract('50000000')
        self.client.force_authenticate(self.bugalter)
        response = self.client.post(f'/api/contracts/{contract.id}/approve/')
        self.assertEqual(response.status_code, 200, response.data)
        contract.refresh_from_db()
        self.assertEqual(contract.status, Contract.Status.READY_FOR_DIDOX)
        # Tarixda avtomatik admin yozuvi (decided_by bo'sh)
        self.assertTrue(
            ContractApproval.objects.filter(
                contract=contract, step=ContractApproval.Step.ADMIN,
                decided_by__isnull=True,
            ).exists(),
        )

        self.client.post(
            f'/api/contracts/{contract.id}/send-didox/',
            {'didox_number': 'DDX-1'}, format='json',
        )
        response = self.client.post(f'/api/contracts/{contract.id}/confirm-didox/')
        self.assertEqual(response.status_code, 200, response.data)
        contract.refresh_from_db()
        self.assertEqual(contract.status, Contract.Status.APPROVED)

    def test_no_way_back_from_pending_didox(self):
        """Didox rad javobi tizimga kiritilmaydi — shartnoma kutib turadi."""
        contract = self._pending_contract()
        self._ready_for_didox(contract)
        self.client.post(
            f'/api/contracts/{contract.id}/send-didox/',
            {'didox_number': 'DDX-1'}, format='json',
        )
        response = self.client.post(f'/api/contracts/{contract.id}/reject/')
        self.assertEqual(response.status_code, 400)
        contract.refresh_from_db()
        self.assertEqual(contract.status, Contract.Status.PENDING_DIDOX)

    def test_legacy_admin_approve_with_prior_didox_goes_straight_to_approved(self):
        """12-§1 eski yozuvlar: Didoxi allaqachon tasdiqlangan bo'lsa, admin
        ikkinchi marta Didoxga yubormasdan to'g'ridan approved qiladi."""
        contract = self._pending_contract()
        Contract.objects.filter(pk=contract.pk).update(
            status=Contract.Status.PENDING_ADMIN,
            didox_number='DDX-OLD', didox_sent_at=now(), didox_accepted_at=now(),
        )
        contract.refresh_from_db()
        self.client.force_authenticate(self.admin)
        response = self.client.post(f'/api/contracts/{contract.id}/approve/')
        self.assertEqual(response.status_code, 200, response.data)
        contract.refresh_from_db()
        self.assertEqual(contract.status, Contract.Status.APPROVED)

    def test_legacy_didox_ignored_after_rejection_and_resubmit(self):
        """QOLGAN-ISHLAR #1 (SHT-00058): Didox eski tartibda tasdiqlangan,
        SO'NG admin rad etgan va qayta yuborilgan — eski Didox izi endi
        haqiqiy emas, admin approve'i to'g'ridan `approved`ga sakramasin,
        Didoxdan qaytadan o'tsin.
        """
        contract = self._pending_contract()
        past = now() - timedelta(days=3)
        Contract.objects.filter(pk=contract.pk).update(
            status=Contract.Status.PENDING_ADMIN,
            didox_number='1/1605', didox_sent_at=past, didox_accepted_at=past,
        )
        contract.refresh_from_db()
        ContractApproval.objects.create(
            contract=contract, step=ContractApproval.Step.ADMIN,
            decision=ContractApproval.Decision.REJECTED,
            comment='Summalar noto\'g\'ri', decided_by=self.admin,
        )
        # Sales tuzatib qayta yubordi — bugalter yana tekshirdi
        Contract.objects.filter(pk=contract.pk).update(
            status=Contract.Status.PENDING_ADMIN,
        )
        contract.refresh_from_db()

        self.client.force_authenticate(self.admin)
        response = self.client.post(f'/api/contracts/{contract.id}/approve/')
        self.assertEqual(response.status_code, 200, response.data)
        contract.refresh_from_db()
        # Eski (rad etishdan oldingi) Didox endi hisobga olinmaydi
        self.assertEqual(contract.status, Contract.Status.READY_FOR_DIDOX)

    def test_prepayment_percent_locked_after_draft(self):
        """B14: foiz faqat qoralamada tuziladi — keyin admin ham o'zgartira olmaydi."""
        contract = Contract.objects.create(
            client=self.mijoz, total_amount=Decimal('50000000'),
            created_by=self.sales,
        )
        self.client.force_authenticate(self.sales)
        response = self.client.patch(
            f'/api/contracts/{contract.id}/',
            {'prepayment_percent': '20'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        contract.refresh_from_db()
        self.assertEqual(contract.prepayment_percent, Decimal('20'))

        Contract.objects.filter(pk=contract.pk).update(
            status=Contract.Status.PENDING_BUGALTER,
        )
        self.client.force_authenticate(self.admin)
        response = self.client.patch(
            f'/api/contracts/{contract.id}/',
            {'prepayment_percent': '10'}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('prepayment_percent', response.data)
        contract.refresh_from_db()
        self.assertEqual(contract.prepayment_percent, Decimal('20'))
