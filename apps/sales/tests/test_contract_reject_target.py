from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.core.models import CompanyProfile, Notification
from apps.inventory.models import Product
from apps.sales.models import Contract, ContractApproval, ContractItem


class ContractRejectTargetTests(APITestCase):
    """20-§2: admin shartnomani sales'ga HAM, bugalterga HAM qaytara oladi —
    `target` parametri, ikkinchisi faqat admin, faqat `pending_admin`dan.
    """

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.admin = User.objects.create_user('adm', password='p', role=User.Role.ADMIN)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.product = Product.objects.create(sku='HP-880', name='HP 880')
        # Admin bosqichi o'tkazib yuborilmasligi uchun — 0 = chegara yo'q,
        # har doim adminga boradi (§11.3)
        profile = CompanyProfile.load()
        profile.admin_approval_threshold = Decimal('0')
        profile.save()

    def _contract(self, status):
        contract = Contract.objects.create(
            client=self.mijoz, total_amount=Decimal('50000000'),
            created_by=self.sales, status=status,
        )
        ContractItem.objects.create(
            contract=contract, product=self.product, quantity=1,
            unit_price=Decimal('50000000'),
        )
        return contract

    def _reject(self, user, contract, target=None, comment='Xato bor'):
        self.client.force_authenticate(user)
        body = {'comment': comment}
        if target is not None:
            body['target'] = target
        return self.client.post(f'/api/contracts/{contract.id}/reject/', body, format='json')

    def test_admin_pending_admin_target_bugalter(self):
        contract = self._contract(Contract.Status.PENDING_ADMIN)
        response = self._reject(self.admin, contract, target='bugalter')
        self.assertEqual(response.status_code, 200, response.data)
        contract.refresh_from_db()
        self.assertEqual(contract.status, Contract.Status.PENDING_BUGALTER)

        approval = contract.approvals.get()
        self.assertEqual(approval.decision, ContractApproval.Decision.REJECTED)
        self.assertEqual(approval.returned_to, 'bugalter')

        notes = Notification.objects.filter(user=self.bugalter, title__contains='qaytardi')
        self.assertTrue(notes.exists())

    def test_admin_pending_admin_target_sales_unchanged(self):
        contract = self._contract(Contract.Status.PENDING_ADMIN)
        response = self._reject(self.admin, contract, target='sales')
        self.assertEqual(response.status_code, 200, response.data)
        contract.refresh_from_db()
        self.assertEqual(contract.status, Contract.Status.REJECTED)
        self.assertEqual(contract.approvals.get().returned_to, '')

    def test_admin_pending_admin_target_omitted_defaults_to_sales(self):
        """Regressiya: eski chaqiruvlar (`target` yo'q) — bugungidek."""
        contract = self._contract(Contract.Status.PENDING_ADMIN)
        response = self._reject(self.admin, contract, target=None)
        self.assertEqual(response.status_code, 200, response.data)
        contract.refresh_from_db()
        self.assertEqual(contract.status, Contract.Status.REJECTED)

    def test_bugalter_cannot_target_bugalter(self):
        contract = self._contract(Contract.Status.PENDING_BUGALTER)
        response = self._reject(self.bugalter, contract, target='bugalter')
        self.assertEqual(response.status_code, 403, response.data)

    def test_bugalter_target_sales_unchanged(self):
        contract = self._contract(Contract.Status.PENDING_BUGALTER)
        response = self._reject(self.bugalter, contract, target='sales')
        self.assertEqual(response.status_code, 200, response.data)
        contract.refresh_from_db()
        self.assertEqual(contract.status, Contract.Status.REJECTED)

    def test_admin_pending_bugalter_target_bugalter_already_there(self):
        contract = self._contract(Contract.Status.PENDING_BUGALTER)
        response = self._reject(self.admin, contract, target='bugalter')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('allaqachon bugalterda', str(response.data['detail']))

    def test_unknown_target_400(self):
        contract = self._contract(Contract.Status.PENDING_ADMIN)
        response = self._reject(self.admin, contract, target='xyz')
        self.assertEqual(response.status_code, 400, response.data)

    def test_returned_to_bugalter_then_approve_goes_back_to_pending_admin(self):
        from apps.sales.services import approve_contract

        contract = self._contract(Contract.Status.PENDING_ADMIN)
        self._reject(self.admin, contract, target='bugalter')
        contract.refresh_from_db()
        self.assertEqual(contract.status, Contract.Status.PENDING_BUGALTER)

        approve_contract(contract, self.bugalter)
        contract.refresh_from_db()
        self.assertEqual(contract.status, Contract.Status.PENDING_ADMIN)

    def test_roadmap_contract_submitted_repeats_unaffected_by_bugalter_return(self):
        """20-§2.1: `contract_submitted.repeats` — faqat sales'ga qaytarishlar."""
        contract = self._contract(Contract.Status.PENDING_ADMIN)
        self._reject(self.admin, contract, target='bugalter')
        contract.refresh_from_db()

        self.client.force_authenticate(self.admin)
        response = self.client.get(f'/api/contracts/{contract.id}/roadmap/')
        self.assertEqual(response.status_code, 200, response.data)
        steps = {s['key']: s for s in response.data['steps']}
        self.assertEqual(steps['contract_submitted']['repeats'], 0)
        self.assertFalse(steps['bugalter_check']['state'] == 'done')

    def test_reservations_kept_when_returned_to_bugalter(self):
        """Bron: `pending_bugalter`da bron turaveradi (bo'shamaydi)."""
        from apps.inventory.models import StockMovement, StockReservation, Warehouse
        from apps.inventory.services import apply_movement, sync_contract_reservations

        warehouse = Warehouse.objects.create(name='Asosiy ombor')
        apply_movement(
            product=self.product, warehouse=warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('5'),
        )
        contract = self._contract(Contract.Status.PENDING_ADMIN)
        sync_contract_reservations(contract)
        self.assertTrue(
            StockReservation.objects.filter(
                contract=contract, product=self.product, status='active',
            ).exists(),
        )

        self._reject(self.admin, contract, target='bugalter')
        self.assertTrue(
            StockReservation.objects.filter(
                contract=contract, product=self.product, status='active',
            ).exists(),
        )
