from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.inventory.models import Product


class ProductPricingTests(APITestCase):
    """§10.2: katalogda narx siyosati — PATCH admin/bugalterga ochildi.

    Avval sale_price ni qo'yadigan joy yo'q edi: stock_price tannarxga
    tushib, shartnoma avtomatik tannarxda ochilardi.
    """

    def setUp(self):
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.product = Product.objects.create(
            sku='HP-880', name='HP 880', cost_price=Decimal('4000000'),
        )

    def _patch(self, body):
        return self.client.patch(
            f'/api/products/{self.product.id}/', body, format='json',
        )

    def test_bugalter_sets_sale_price_and_reorder_level(self):
        self.client.force_authenticate(self.bugalter)
        response = self._patch({'sale_price': '5500000', 'reorder_level': 2})
        self.assertEqual(response.status_code, 200, response.data)

        self.product.refresh_from_db()
        self.assertEqual(self.product.sale_price, Decimal('5500000'))
        self.assertEqual(self.product.reorder_level, 2)
        # Endi stock_price sotuv narxini qaytaradi — tannarxni emas
        self.assertEqual(self.product.stock_price, Decimal('5500000'))

    def test_sales_cannot_patch(self):
        self.client.force_authenticate(self.sales)
        self.assertEqual(self._patch({'sale_price': '1'}).status_code, 403)

    def test_identity_fields_stay_read_only(self):
        """sku/nom/kind o'zgarmaydi — PATCH faqat narx siyosati uchun."""
        self.client.force_authenticate(self.bugalter)
        response = self._patch({'sku': 'HACK-1', 'name': 'Boshqa nom'})
        self.assertEqual(response.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.sku, 'HP-880')
        self.assertEqual(self.product.name, 'HP 880')

    def test_post_is_not_routed(self):
        """Katalogga POST yo'q — mahsulot faqat buyurtma orqali tug'iladi."""
        self.client.force_authenticate(self.bugalter)
        response = self.client.post('/api/products/', {'sku': 'X', 'name': 'X'})
        self.assertEqual(response.status_code, 405)
