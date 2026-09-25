from datetime import date
from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.configurator.models import Act, Configuration
from apps.inventory.models import Product, Warehouse


class ConfigurationActStatusFieldTests(APITestCase):
    """21-§5: `ConfigurationSerializer`da `act_status` — ACT holati."""

    def setUp(self):
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.base = Product.objects.create(
            sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE,
            sale_price=Decimal('12000000'),
        )

    def test_act_status_matches_linked_act(self):
        act = Act.objects.create(number='ACT-1', title='ACT', issued_at=date.today())
        configuration = Configuration.objects.create(
            base_product=self.base, warehouse=self.warehouse,
            created_by=self.engineer, act=act,
        )
        self.client.force_authenticate(self.engineer)
        response = self.client.get(f'/api/configurations/{configuration.id}/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['act_status'], act.status)

    def test_act_status_null_when_no_act(self):
        configuration = Configuration.objects.create(
            base_product=self.base, warehouse=self.warehouse, created_by=self.engineer,
        )
        self.client.force_authenticate(self.engineer)
        response = self.client.get(f'/api/configurations/{configuration.id}/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNone(response.data['act_status'])
