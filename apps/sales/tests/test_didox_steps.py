from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.core.models import CompanyProfile
from apps.inventory.models import Product
from apps.sales.models import Contract, ContractApproval, ContractItem


class DidoxStepsTests(APITestCase):
    """YANGI-OQIM B3: Didox bitta emas, ikki qadam — yubordim / tasdiqladi."""

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

    def test_send_didox_requires_number_and_moves_status(self):
        contract = self._pending_contract()
        self.client.force_authenticate(self.bugalter)
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

    def test_confirm_didox_goes_to_admin_then_approved(self):
        contract = self._pending_contract()
        self.client.force_authenticate(self.bugalter)
        self.client.post(
            f'/api/contracts/{contract.id}/send-didox/',
            {'didox_number': 'DDX-77'}, format='json',
        )
        response = self.client.post(f'/api/contracts/{contract.id}/confirm-didox/')
        self.assertEqual(response.status_code, 200, response.data)
        contract.refresh_from_db()
        self.assertEqual(contract.status, Contract.Status.PENDING_ADMIN)
        self.assertIsNotNone(contract.didox_accepted_at)

        self.client.force_authenticate(self.admin)
        response = self.client.post(f'/api/contracts/{contract.id}/approve/')
        self.assertEqual(response.status_code, 200, response.data)
        contract.refresh_from_db()
        self.assertEqual(contract.status, Contract.Status.APPROVED)

    def test_confirm_didox_skips_admin_under_threshold(self):
        """§11.3 chegara mantig'i confirm-didox'da ham ishlaydi."""
        profile = CompanyProfile.load()
        profile.admin_approval_threshold = Decimal('100000000')
        profile.save()
        contract = self._pending_contract('50000000')
        self.client.force_authenticate(self.bugalter)
        self.client.post(
            f'/api/contracts/{contract.id}/send-didox/',
            {'didox_number': 'DDX-1'}, format='json',
        )
        response = self.client.post(f'/api/contracts/{contract.id}/confirm-didox/')
        self.assertEqual(response.status_code, 200, response.data)
        contract.refresh_from_db()
        self.assertEqual(contract.status, Contract.Status.APPROVED)
        # Tarixda avtomatik admin yozuvi (decided_by bo'sh)
        self.assertTrue(
            ContractApproval.objects.filter(
                contract=contract, step=ContractApproval.Step.ADMIN,
                decided_by__isnull=True,
            ).exists(),
        )

    def test_no_way_back_from_pending_didox(self):
        """Didox rad javobi tizimga kiritilmaydi — shartnoma kutib turadi."""
        contract = self._pending_contract()
        self.client.force_authenticate(self.bugalter)
        self.client.post(
            f'/api/contracts/{contract.id}/send-didox/',
            {'didox_number': 'DDX-1'}, format='json',
        )
        response = self.client.post(f'/api/contracts/{contract.id}/reject/')
        self.assertEqual(response.status_code, 400)
        contract.refresh_from_db()
        self.assertEqual(contract.status, Contract.Status.PENDING_DIDOX)

    def test_legacy_one_step_approve_still_works(self):
        """B11: eski yo'l ham qabul qilinadi — pending_bugalter'dan to'g'ridan approve."""
        contract = self._pending_contract()
        self.client.force_authenticate(self.bugalter)
        response = self.client.post(
            f'/api/contracts/{contract.id}/approve/',
            {'didox_number': 'DDX-OLD'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        contract.refresh_from_db()
        self.assertEqual(contract.status, Contract.Status.PENDING_ADMIN)

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
