from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.core.models import CompanyProfile, Notification
from apps.inventory.models import Product
from apps.procurement.models import Replenishment, ReplenishmentApproval, ReplenishmentItem


class ReplenishmentThresholdTests(APITestCase):
    """TOPSHIRIQ #2: chegaradan kichik TLD admin tasdig'isiz o'tadi.

    Shartnomadagi qoidalar aynan: QQS+xarajatlar bilan, faqat UZS,
    0 — chegara yo'q, tarixda avtomatik yozuv, xabar yolg'on gapirmaydi.
    """

    def setUp(self):
        from apps.inventory.services import main_warehouse

        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.admin = User.objects.create_user('adm', password='p', role=User.Role.ADMIN)
        self.buyurtmachi = User.objects.create_user(
            'buy', password='p', role=User.Role.SUPPLIER,
        )
        self.warehouse = main_warehouse()
        self.gpu = Product.objects.create(sku='GPU-1', name='GPU')

        profile = CompanyProfile.load()
        profile.replenishment_approval_threshold = Decimal('1000000')  # 1 mln
        profile.save()

    def _make_pending(self, unit_price, currency='UZS'):
        replenishment = Replenishment.objects.create(
            warehouse=self.warehouse, status=Replenishment.Status.PENDING_BUGALTER,
            currency=currency, created_by=self.buyurtmachi,
        )
        ReplenishmentItem.objects.create(
            replenishment=replenishment, product=self.gpu,
            quantity=1, unit_price=Decimal(unit_price),
        )
        return replenishment

    def _approve(self, replenishment):
        self.client.force_authenticate(self.bugalter)
        return self.client.post(f'/api/replenishments/{replenishment.id}/approve/')

    def test_small_replenishment_skips_admin(self):
        replenishment = self._make_pending('675000')
        response = self._approve(replenishment)
        self.assertEqual(response.data['status'], Replenishment.Status.APPROVED)

        # Tarix jim qolmaydi: avtomatik admin yozuvi, decided_by bo'sh
        auto = ReplenishmentApproval.objects.get(
            replenishment=replenishment, step=ReplenishmentApproval.Step.ADMIN,
        )
        self.assertIsNone(auto.decided_by)
        self.assertIn('chegara', auto.comment)

        # Xabar "Admin tasdiqladi" demaydi
        note = Notification.objects.get(
            user=self.bugalter, title__contains="to'lov bosqichi",
        )
        self.assertNotIn('Admin tasdiqladi', note.message)
        self.assertIn('chegaradan past', note.message)

    def test_big_replenishment_goes_to_admin(self):
        replenishment = self._make_pending('5000000')
        response = self._approve(replenishment)
        self.assertEqual(response.data['status'], Replenishment.Status.PENDING_ADMIN)

    def test_foreign_currency_always_goes_to_admin(self):
        replenishment = self._make_pending('100', currency='USD')
        response = self._approve(replenishment)
        self.assertEqual(response.data['status'], Replenishment.Status.PENDING_ADMIN)

    def test_zero_threshold_keeps_current_flow(self):
        profile = CompanyProfile.load()
        profile.replenishment_approval_threshold = Decimal('0')
        profile.save()
        replenishment = self._make_pending('675000')
        response = self._approve(replenishment)
        self.assertEqual(response.data['status'], Replenishment.Status.PENDING_ADMIN)

    def test_contract_threshold_is_separate(self):
        """Shartnoma chegarasi TLD ga ta'sir qilmaydi — ikkita alohida maydon."""
        profile = CompanyProfile.load()
        profile.replenishment_approval_threshold = Decimal('0')
        profile.admin_approval_threshold = Decimal('100000000')  # 100 mln
        profile.save()
        replenishment = self._make_pending('675000')
        response = self._approve(replenishment)
        # Shartnoma chegarasi katta bo'lsa ham TLD adminga boradi
        self.assertEqual(response.data['status'], Replenishment.Status.PENDING_ADMIN)
