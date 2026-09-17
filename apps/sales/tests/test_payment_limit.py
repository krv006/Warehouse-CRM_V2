from decimal import Decimal

from django.utils.timezone import localdate

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.finance.models import CashTransaction
from apps.inventory.models import Product
from apps.sales.models import Contract, ContractItem, ContractPayment


class PaymentLimitTests(APITestCase):
    """4-to'plam §3: to'lov qoldiqdan oshmaydi — kassaga yo'q pul yozilmaydi."""

    def setUp(self):
        self.sales = User.objects.create_user('sales', password='p', role=User.Role.SALES)
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.client_obj = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.product = Product.objects.create(sku='HP-880', name='HP 880')
        self.client.force_authenticate(self.bugalter)

    def _contract(self, total='9296000', status=Contract.Status.APPROVED):
        contract = Contract.objects.create(
            client=self.client_obj, total_amount=Decimal(total),
            created_by=self.sales, status=status,
        )
        ContractItem.objects.create(
            contract=contract, product=self.product, quantity=1,
            unit_price=Decimal(total),
        )
        return contract

    def _pay(self, contract, amount):
        return self.client.post(
            f'/api/contracts/{contract.id}/confirm-payment/',
            {'amount': str(amount)}, format='json',
        )

    def test_over_balance_rejected_nothing_written(self):
        """Jonli xato (SHT-00036): 9 296 000 lik shartnomaga 653 508 800 o'tgan edi."""
        contract = self._contract('9296000')
        response = self._pay(contract, '653508800')
        self.assertEqual(response.status_code, 400)
        self.assertIn('amount', response.data)
        # Kassaga ham, to'lovlar tarixiga ham hech nima yozilmadi
        self.assertFalse(ContractPayment.objects.exists())
        self.assertFalse(CashTransaction.objects.exists())

    def test_exact_balance_passes_and_completes(self):
        """Aynan qoldiqqa teng summa o'tadi — yetkazilgan shartnoma yopiladi."""
        contract = self._contract('9296000')
        contract.delivered_at = localdate()
        contract.save()
        response = self._pay(contract, '9296000')
        self.assertEqual(response.status_code, 200, response.data)
        contract.refresh_from_db()
        self.assertEqual(contract.balance, Decimal('0'))
        self.assertEqual(contract.status, Contract.Status.COMPLETED)

    def test_zero_and_negative_rejected(self):
        contract = self._contract()
        for amount in ('0', '-5000'):
            response = self._pay(contract, amount)
            self.assertEqual(response.status_code, 400, amount)
            self.assertIn('amount', response.data)
        self.assertFalse(ContractPayment.objects.exists())

    def test_contract_payments_endpoint_same_rule(self):
        """POST /contract-payments/ ham xuddi shu yo'ldan o'tadi — bir xil rad."""
        contract = self._contract('9296000')
        response = self.client.post('/api/contract-payments/', {
            'contract': contract.id, 'amount': '10000000',
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('amount', response.data)

    def test_legacy_negative_balance_gives_400_not_500(self):
        """Bazadagi manfiy balansli eski shartnoma: 400 va tushunarli xabar."""
        contract = self._contract('9296000', status=Contract.Status.ACTIVE)
        # Eski davrda yozilib ketgan ortiqcha to'lov — servis chetlab o'tilgan
        from django.utils.timezone import now

        ContractPayment.objects.create(
            contract=contract, amount=Decimal('653508800'),
            paid_at=now(), created_by=self.bugalter,
        )
        self.assertLess(contract.balance, 0)
        response = self._pay(contract, '1000')
        self.assertEqual(response.status_code, 400)
        self.assertIn('qoldiq 0', str(response.data['amount']))
