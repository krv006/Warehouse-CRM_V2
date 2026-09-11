from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.inventory.models import Product
from apps.sales.models import Contract


class ContractVatTests(APITestCase):
    """Shartnomada QQS: qatorda 12% default, yig'indilar va rollarga ko'rinish."""

    def setUp(self):
        self.sales = User.objects.create_user('sales', password='p', role=User.Role.SALES)
        self.bugalter = User.objects.create_user('bugalter', password='p', role=User.Role.BUGALTER)
        self.client_obj = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.product = Product.objects.create(
            sku='ADS-1', name='adas', sale_price=Decimal('5000000'),
        )
        self.client.force_authenticate(self.sales)

    def _create_contract(self, **item_extra):
        payload = {
            'client': self.client_obj.id,
            'items': [{
                'product': self.product.id,
                'quantity': 1,
                'unit_price': '5000000',
                **item_extra,
            }],
        }
        return self.client.post('/api/contracts/', payload, format='json')

    def test_default_vat_12_percent(self):
        """Rasmdagi misol: 5 000 000 + 12% QQS = 5 600 000."""
        response = self._create_contract()
        self.assertEqual(response.status_code, 201, response.data)
        item = response.data['items'][0]
        self.assertEqual(Decimal(item['vat_percent']), Decimal('12'))
        self.assertEqual(Decimal(item['vat_amount']), Decimal('600000.00'))
        self.assertEqual(Decimal(item['total_with_vat']), Decimal('5600000.00'))

        self.assertEqual(Decimal(response.data['items_total']), Decimal('5000000'))
        self.assertEqual(Decimal(response.data['vat_total']), Decimal('600000.00'))
        self.assertEqual(Decimal(response.data['items_total_with_vat']), Decimal('5600000.00'))

    def test_total_amount_synced_with_vat(self):
        """Summa berilmasa shartnoma jami QQS bilan olinadi — mijoz to'laydigan pul."""
        response = self._create_contract()
        contract = Contract.objects.get(pk=response.data['id'])
        self.assertEqual(contract.total_amount, Decimal('5600000.00'))
        # Oldindan to'lov ham QQS bilan jamidan: 30% (1 mlrd dan kam)
        self.assertEqual(contract.prepayment_amount, Decimal('1680000.00'))

    def test_zero_vat_for_exempt_product(self):
        """Imtiyozli mahsulotga 0% qo'yish mumkin."""
        response = self._create_contract(vat_percent='0')
        item = response.data['items'][0]
        self.assertEqual(Decimal(item['vat_amount']), Decimal('0.00'))
        self.assertEqual(Decimal(item['total_with_vat']), Decimal('5000000.00'))
        self.assertEqual(
            Decimal(response.data['items_total_with_vat']), Decimal('5000000.00'),
        )

    def test_vat_fields_hidden_from_bugalter(self):
        """TZ: qator narxlari bugalterdan yashirin — QQS maydonlari ham."""
        contract_id = self._create_contract().data['id']
        self.client.force_authenticate(self.bugalter)
        response = self.client.get(f'/api/contracts/{contract_id}/')
        item = response.data['items'][0]
        for field in ('unit_price', 'subtotal', 'vat_percent', 'vat_amount', 'total_with_vat'):
            self.assertNotIn(field, item, field)
