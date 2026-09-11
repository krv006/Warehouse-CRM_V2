from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.inventory.models import Product
from apps.procurement.models import Replenishment


class ReplenishmentVatTests(APITestCase):
    """To'ldirishda QQS: default 0, buyurtmachi ta'minotchi hisobiga qarab kiritadi."""

    def setUp(self):
        self.buyurtmachi = User.objects.create_user(
            'buyurtmachi', password='p', role=User.Role.SUPPLIER,
        )
        self.product = Product.objects.create(
            sku='SSD-1', name='SSD disk', kind=Product.Kind.COMPONENT,
            cost_price=Decimal('1000000'),
        )
        self.client.force_authenticate(self.buyurtmachi)
        self.replenishment_id = self.client.post('/api/replenishments/', {
            'supplier': 'Etuf MCHJ',
        }).data['id']

    def _add_item(self, **extra):
        return self.client.post('/api/replenishment-items/', {
            'replenishment': self.replenishment_id,
            'product': self.product.id,
            'quantity': 2,
            'unit_price': '1000000',
            **extra,
        })

    def test_vat_default_zero(self):
        """QQS yuborilmasa 0 — ta'minotchi narxi qanday bo'lsa shunday qoladi."""
        response = self._add_item()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Decimal(response.data['vat_percent']), Decimal('0'))
        self.assertEqual(Decimal(response.data['vat_amount']), Decimal('0.00'))
        self.assertEqual(Decimal(response.data['total_with_vat']), Decimal('2000000.00'))

    def test_vat_entered_by_buyurtmachi(self):
        """Buyurtmachi 12% kiritsa: 2 000 000 + 240 000 QQS = 2 240 000."""
        response = self._add_item(vat_percent='12')
        self.assertEqual(Decimal(response.data['vat_amount']), Decimal('240000.00'))
        self.assertEqual(Decimal(response.data['total_with_vat']), Decimal('2240000.00'))

        detail = self.client.get(f'/api/replenishments/{self.replenishment_id}/').data
        self.assertEqual(Decimal(detail['items_total']), Decimal('2000000.00'))
        self.assertEqual(Decimal(detail['vat_total']), Decimal('240000.00'))
        self.assertEqual(Decimal(detail['items_total_with_vat']), Decimal('2240000.00'))
        self.assertEqual(Decimal(detail['total_amount']), Decimal('2240000.00'))

    def test_total_amount_includes_vat_and_costs(self):
        """Jami = QQS bilan qatorlar + logistika + boshqa xarajatlar (to'lov shu summadan)."""
        self._add_item(vat_percent='12')
        self.client.patch(f'/api/replenishments/{self.replenishment_id}/', {
            'logistics_cost': '100000', 'other_cost': '50000',
        })
        replenishment = Replenishment.objects.get(pk=self.replenishment_id)
        self.assertEqual(replenishment.total_amount, Decimal('2390000.00'))
