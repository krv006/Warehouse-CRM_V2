from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.finance.models import CashTransaction
from apps.inventory.models import Product, Warehouse
from apps.inventory.services import available_quantity
from apps.purchases.models import Purchase, PurchaseItem


class PurchaseStatusGuardTests(APITestCase):
    """§10.6: KIR holati faqat oldinga yuradi — received'dan chiqib bo'lmaydi.

    Avval PATCH {"status": "draft"} received hujjatga ham o'tar va receive
    qayta chaqirilsa ombor + kassa ikki marta yozilardi.
    """

    def setUp(self):
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.product = Product.objects.create(sku='GPU-32', name='GPU 32')
        self.purchase = Purchase.objects.create(
            supplier='Etuf', warehouse=self.warehouse, type=Purchase.Type.LOCAL,
        )
        PurchaseItem.objects.create(
            purchase=self.purchase, product=self.product,
            quantity=Decimal('3'), unit_price=Decimal('4000000'),
        )
        self.client.force_authenticate(self.bugalter)

    def _patch_status(self, status):
        return self.client.patch(
            f'/api/purchases/{self.purchase.id}/', {'status': status}, format='json',
        )

    def test_received_cannot_go_back_to_draft(self):
        self.client.post(f'/api/purchases/{self.purchase.id}/receive/')
        response = self._patch_status('draft')
        self.assertEqual(response.status_code, 400)
        self.purchase.refresh_from_db()
        self.assertEqual(self.purchase.status, Purchase.Status.RECEIVED)
        # Ombor va kassa bitta martalik bo'lib qoldi
        self.assertEqual(available_quantity(self.product, self.warehouse), Decimal('3.00'))
        self.assertEqual(CashTransaction.objects.count(), 1)

    def test_received_via_patch_is_blocked(self):
        """`received` ga faqat receive olib boradi — PATCH bilan emas."""
        response = self._patch_status('received')
        self.assertEqual(response.status_code, 400)
        # receive chaqirilmagani uchun omborga hech narsa kirmagan
        self.assertEqual(available_quantity(self.product, self.warehouse), 0)

    def test_forward_transition_is_allowed(self):
        response = self._patch_status('ordered')
        self.assertEqual(response.status_code, 200, response.data)
        response = self._patch_status('in_transit')
        self.assertEqual(response.status_code, 200, response.data)
        # Orqaga emas
        self.assertEqual(self._patch_status('ordered').status_code, 400)
