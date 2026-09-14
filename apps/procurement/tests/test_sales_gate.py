from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.core.models import Notification
from apps.inventory.models import Product
from apps.procurement.models import Replenishment, ReplenishmentApproval, ReplenishmentItem


class SalesGateTests(APITestCase):
    """Mijoz buyurtmasidan ochilgan hisob: buyurtmachi -> sales -> bugalter -> admin.

    Sales mijoz bilan narxlarni kelishmasdan bugalter/adminga hech narsa
    tushmaydi; oddiy ombor to'ldirish esa eskicha to'g'ri bugalterga boradi.
    """

    def setUp(self):
        from apps.configurator.models import Configuration
        from apps.inventory.services import main_warehouse

        self.buyurtmachi = User.objects.create_user(
            'buyurtmachi', password='p', role=User.Role.SUPPLIER,
        )
        self.sales = User.objects.create_user('sales', password='p', role=User.Role.SALES)
        self.bugalter = User.objects.create_user('bugalter', password='p', role=User.Role.BUGALTER)
        self.admin = User.objects.create_user('admin', password='p', role=User.Role.ADMIN)

        warehouse = main_warehouse()
        base = Product.objects.create(sku='HP-1', name='HP 880', kind=Product.Kind.MACHINE)
        self.configuration = Configuration.objects.create(
            base_product=base, warehouse=warehouse, created_by=self.sales,
        )
        component = Product.objects.create(
            sku='GPU-1', name='GPU 32GB', kind=Product.Kind.COMPONENT,
            cost_price=Decimal('4000000'),
        )

        # Konfiguratsiyadan ochilgan hisob (engineer request-procurement qilgani kabi)
        self.client_order = Replenishment.objects.create(
            warehouse=warehouse, configuration=self.configuration,
            created_by=self.buyurtmachi,
        )
        ReplenishmentItem.objects.create(
            replenishment=self.client_order, product=component,
            quantity=1, unit_price=Decimal('4000000'),
        )

        # Oddiy ombor to'ldirish — konfiguratsiyasiz
        self.plain = Replenishment.objects.create(
            warehouse=warehouse, created_by=self.buyurtmachi,
        )
        ReplenishmentItem.objects.create(
            replenishment=self.plain, product=component,
            quantity=2, unit_price=Decimal('4000000'),
        )

    def _submit(self, replenishment):
        self.client.force_authenticate(self.buyurtmachi)
        return self.client.post(f'/api/replenishments/{replenishment.id}/submit/')

    def test_client_order_goes_to_sales_first(self):
        """Konfiguratsiyali hisob submit'da sales'ga boradi va sales'ga xabar tushadi."""
        response = self._submit(self.client_order)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], Replenishment.Status.PENDING_SALES)

        note = Notification.objects.get(entity='Replenishment', user=self.sales)
        self.assertIn('mijoz roziligi', note.title)

    def test_plain_replenishment_skips_sales(self):
        """Oddiy to'ldirish eskicha — to'g'ridan-to'g'ri bugalterga."""
        response = self._submit(self.plain)
        self.assertEqual(response.data['status'], Replenishment.Status.PENDING_BUGALTER)
        self.assertFalse(Notification.objects.filter(user=self.sales).exists())

    def test_bugalter_cannot_approve_before_sales(self):
        """Mijoz roziligisiz bugalter tasdiqlay olmaydi — unga ish tushmaydi."""
        self._submit(self.client_order)
        self.client.force_authenticate(self.bugalter)
        response = self.client.post(f'/api/replenishments/{self.client_order.id}/approve/')
        self.assertEqual(response.status_code, 403)

    def test_full_chain_sales_then_bugalter_then_admin(self):
        """To'liq zanjir: sales -> bugalter -> admin -> approved; tarixda sales bosqichi."""
        self._submit(self.client_order)

        self.client.force_authenticate(self.sales)
        response = self.client.post(
            f'/api/replenishments/{self.client_order.id}/approve/',
            {'comment': 'Mijoz narxlarga rozi'},
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], Replenishment.Status.PENDING_BUGALTER)

        self.client.force_authenticate(self.bugalter)
        response = self.client.post(f'/api/replenishments/{self.client_order.id}/approve/')
        self.assertEqual(response.data['status'], Replenishment.Status.PENDING_ADMIN)

        self.client.force_authenticate(self.admin)
        response = self.client.post(f'/api/replenishments/{self.client_order.id}/approve/')
        self.assertEqual(response.data['status'], Replenishment.Status.APPROVED)

        steps = list(
            ReplenishmentApproval.objects.filter(replenishment=self.client_order)
            .values_list('step', flat=True)
        )
        self.assertEqual(steps, [
            ReplenishmentApproval.Step.SALES,
            ReplenishmentApproval.Step.BUGALTER,
            ReplenishmentApproval.Step.ADMIN,
        ])

    def test_sales_rejects_client_refused(self):
        """Mijoz rozi bo'lmasa sales qaytaradi — buyurtmachiga xabar, hisob qoralamaga."""
        self._submit(self.client_order)
        self.client.force_authenticate(self.sales)
        response = self.client.post(
            f'/api/replenishments/{self.client_order.id}/reject/',
            {'comment': 'Mijoz narxdan voz kechdi'},
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], Replenishment.Status.REJECTED)
        self.assertTrue(
            Notification.objects.filter(
                user=self.buyurtmachi, title__contains='qaytarildi',
            ).exists()
        )

    def test_sales_reads_replenishment(self):
        """Sales hisobni ochib ko'ra oladi (mijoz bilan kelishish uchun)."""
        self.client.force_authenticate(self.sales)
        response = self.client.get(f'/api/replenishments/{self.client_order.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['configuration'], self.configuration.id)
