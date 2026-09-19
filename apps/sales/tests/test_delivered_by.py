from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.inventory.models import Product, StockMovement, Warehouse
from apps.inventory.services import apply_movement
from apps.sales.models import Contract, ContractItem


class DeliveredByTests(APITestCase):
    """10-to'plam §7: yetkazgan odam shartnomani yopilguncha ko'rib turadi."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.supplier = User.objects.create_user('buy', password='p', role=User.Role.SUPPLIER)
        self.supplier2 = User.objects.create_user('buy2', password='p', role=User.Role.SUPPLIER)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.product = Product.objects.create(
            sku='HP-880', name='HP 880', sale_price=Decimal('5000000'),
        )
        apply_movement(
            product=self.product, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('5'),
        )
        # Faol, YETKAZILMAGAN, balansi ochiq shartnoma
        self.contract = Contract.objects.create(
            client=self.mijoz, total_amount=Decimal('100000000'),
            created_by=self.sales, status=Contract.Status.ACTIVE,
        )
        ContractItem.objects.create(
            contract=self.contract, product=self.product, quantity=1,
            unit_price=Decimal('5000000'),
        )

    def test_ship_records_who_and_keeps_visibility(self):
        """Yetkazgan zahoti 404 bo'lib qolmasin — ish yopilguncha ko'rinadi."""
        self.client.force_authenticate(self.supplier)
        response = self.client.post(f'/api/contracts/{self.contract.id}/ship/')
        self.assertEqual(response.status_code, 200, response.data)

        self.contract.refresh_from_db()
        self.assertEqual(self.contract.delivered_by, self.supplier)
        # Balans ochiq — shartnoma hali yopilmagan (`active`)
        self.assertEqual(self.contract.status, Contract.Status.ACTIVE)

        # Yetkazgan buyurtmachi ko'rishda davom etadi
        response = self.client.get(f'/api/contracts/{self.contract.id}/')
        self.assertEqual(response.status_code, 200)
        numbers = [
            row['number']
            for row in self.client.get('/api/contracts/').data['results']
        ]
        self.assertIn(self.contract.number, numbers)

        # Boshqa buyurtmachiga esa ko'rinmaydi — bu navbat emas, uning izi
        self.client.force_authenticate(self.supplier2)
        response = self.client.get(f'/api/contracts/{self.contract.id}/')
        self.assertEqual(response.status_code, 404)

    def test_roadmap_ship_step_gets_name(self):
        """Roadmapdagi `ship` qadami endi ism bilan keladi."""
        self.client.force_authenticate(self.supplier)
        self.client.post(f'/api/contracts/{self.contract.id}/ship/')
        steps = {
            s['key']: s for s in self.client.get(
                f'/api/contracts/{self.contract.id}/roadmap/',
            ).data['steps']
        }
        self.assertEqual(steps['ship']['state'], 'done')
        self.assertEqual(steps['ship']['actor']['full_name'], 'buy')
