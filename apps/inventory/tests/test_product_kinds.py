from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.inventory.models import Product, ProductSpec, Warehouse
from apps.procurement.models import Replenishment


class TwoKindsOfIntakeTests(APITestCase):
    """Ikki xil kirim: Butlovchi (default) va Tayyor model (product_kind bilan)."""

    def setUp(self):
        self.buyurtmachi = User.objects.create_user(
            'buy', password='p', role=User.Role.SUPPLIER,
        )
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.replenishment = Replenishment.objects.create(
            warehouse=self.warehouse, created_by=self.buyurtmachi,
        )
        self.client.force_authenticate(self.buyurtmachi)

    def _order(self, **extra):
        return self.client.post('/api/replenishment-items/', {
            'replenishment': self.replenishment.id,
            'quantity': 2, 'unit_price': '1000000',
            **extra,
        }, format='json')

    def test_new_product_defaults_to_component(self):
        response = self._order(product_name='SSD 2 TB')
        self.assertEqual(response.status_code, 201, response.data)
        product = Product.objects.get(name='SSD 2 TB')
        self.assertEqual(product.kind, Product.Kind.COMPONENT)
        self.assertEqual(response.data['product_kind_display'], 'Butlovchi')

    def test_new_product_as_machine(self):
        """Tayyor modelni ham kirim qilib bo'ladi — product_kind='machine'."""
        response = self._order(product_name='HP 990 kompyuter', product_kind='machine')
        self.assertEqual(response.status_code, 201, response.data)
        product = Product.objects.get(name='HP 990 kompyuter')
        self.assertEqual(product.kind, Product.Kind.MACHINE)
        self.assertEqual(response.data['product_kind_display'], 'Tayyor model')

    def test_invalid_kind_is_400(self):
        response = self._order(product_name='X', product_kind='mebel')
        self.assertEqual(response.status_code, 400)
        self.assertIn('product_kind', response.data)


class ProductSpecWriteTests(APITestCase):
    """Tayyor model tarkibi (ichidagi configlar) — engineer kiritadi."""

    def setUp(self):
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.buyurtmachi = User.objects.create_user(
            'buy', password='p', role=User.Role.SUPPLIER,
        )
        self.machine = Product.objects.create(
            sku='HP-990', name='HP 990', kind=Product.Kind.MACHINE,
        )
        self.ssd = Product.objects.create(
            sku='SSD-1TB', name='SSD 1 TB', kind=Product.Kind.COMPONENT,
        )
        self.client.force_authenticate(self.engineer)

    def test_engineer_adds_spec(self):
        response = self.client.post('/api/product-specs/', {
            'product': self.machine.id, 'component': self.ssd.id,
            'label': 'SSD', 'quantity': 2,
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        spec = ProductSpec.objects.get()
        self.assertEqual(spec.product, self.machine)
        self.assertEqual(spec.quantity, 2)

    def test_spec_with_new_component_name(self):
        """Tarkibga bazada yo'q butlovchini ham yozsa bo'ladi — katalogga tushadi."""
        response = self.client.post('/api/product-specs/', {
            'product': self.machine.id,
            'new_component_name': 'Quvvat bloki 850W',
            'label': 'PSU', 'quantity': 1,
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        component = Product.objects.get(name='Quvvat bloki 850W')
        self.assertEqual(component.kind, Product.Kind.COMPONENT)
        self.assertEqual(ProductSpec.objects.get().component, component)

    def test_spec_only_for_machines(self):
        """Butlovchiga tarkib qo'shib bo'lmaydi."""
        response = self.client.post('/api/product-specs/', {
            'product': self.ssd.id, 'component': self.machine.id,
            'label': 'X', 'quantity': 1,
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('product', response.data)

    def test_spec_requires_component_or_name(self):
        response = self.client.post('/api/product-specs/', {
            'product': self.machine.id, 'label': 'X', 'quantity': 1,
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('component', response.data)

    def test_buyurtmachi_cannot_write_specs(self):
        self.client.force_authenticate(self.buyurtmachi)
        response = self.client.post('/api/product-specs/', {
            'product': self.machine.id, 'component': self.ssd.id,
            'label': 'SSD', 'quantity': 1,
        }, format='json')
        self.assertEqual(response.status_code, 403)

    def test_engineer_edits_and_deletes_spec(self):
        spec = ProductSpec.objects.create(
            product=self.machine, component=self.ssd, label='SSD', quantity=1,
        )
        response = self.client.patch(
            f'/api/product-specs/{spec.id}/', {'quantity': 3}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(ProductSpec.objects.get().quantity, 3)
        self.assertEqual(
            self.client.delete(f'/api/product-specs/{spec.id}/').status_code, 204,
        )
