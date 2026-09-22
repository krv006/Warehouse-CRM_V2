from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.utils.timezone import now

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.inventory.models import Product
from apps.sales.models import Contract, ContractApproval, ContractItem


class FixStaleDidoxTests(APITestCase):
    """QOLGAN-ISHLAR #1 (SHT-00058): eski Didox iziga tayanib xato
    `approved` bo'lgan shartnomalarni `ready_for_didox`ga qaytaradi."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.admin = User.objects.create_user('adm', password='p', role=User.Role.ADMIN)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.product = Product.objects.create(sku='HP-880', name='HP 880')

    def _contract(self, total='50000000'):
        contract = Contract.objects.create(
            client=self.mijoz, total_amount=Decimal(total), created_by=self.sales,
        )
        ContractItem.objects.create(
            contract=contract, product=self.product, quantity=1, unit_price=Decimal(total),
        )
        return contract

    def test_fixes_stale_record_like_sht_00058(self):
        past = now() - timedelta(days=3)
        contract = self._contract()
        Contract.objects.filter(pk=contract.pk).update(
            status=Contract.Status.APPROVED,
            didox_number='1/1605', didox_sent_at=past, didox_accepted_at=past,
        )
        ContractApproval.objects.create(
            contract=contract, step=ContractApproval.Step.ADMIN,
            decision=ContractApproval.Decision.REJECTED,
            comment='xato', decided_by=self.admin,
        )

        out = StringIO()
        call_command('fix_stale_didox', stdout=out)

        contract.refresh_from_db()
        self.assertEqual(contract.status, Contract.Status.READY_FOR_DIDOX)
        self.assertIn(contract.number, out.getvalue())

    def test_dry_run_does_not_write(self):
        past = now() - timedelta(days=3)
        contract = self._contract()
        Contract.objects.filter(pk=contract.pk).update(
            status=Contract.Status.APPROVED,
            didox_number='1/1605', didox_sent_at=past, didox_accepted_at=past,
        )
        ContractApproval.objects.create(
            contract=contract, step=ContractApproval.Step.ADMIN,
            decision=ContractApproval.Decision.REJECTED,
            comment='xato', decided_by=self.admin,
        )

        call_command('fix_stale_didox', '--dry-run')

        contract.refresh_from_db()
        self.assertEqual(contract.status, Contract.Status.APPROVED)

    def test_leaves_genuinely_valid_record_untouched(self):
        """Rad etilmagan (haqiqiy) eski yozuv tegilmaydi."""
        contract = self._contract()
        Contract.objects.filter(pk=contract.pk).update(
            status=Contract.Status.APPROVED,
            didox_number='DDX-1', didox_sent_at=now(), didox_accepted_at=now(),
        )

        call_command('fix_stale_didox')

        contract.refresh_from_db()
        self.assertEqual(contract.status, Contract.Status.APPROVED)
