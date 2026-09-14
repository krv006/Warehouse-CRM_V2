from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.core.models import Notification
from apps.inventory.models import Product
from apps.procurement.models import Replenishment, ReplenishmentItem


class ChainNotificationTests(APITestCase):
    """Tasdiq zanjirida navbat kimga o'tsa, o'sha xabar oladi.

    Front topgan xato: bugalter tasdiqlab adminga yuborganda adminga
    bildirishnoma tushmas edi — endi har bir bosqich egasi xabar oladi.
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
        self.client_order = Replenishment.objects.create(
            warehouse=warehouse, configuration=self.configuration,
            created_by=self.buyurtmachi,
        )
        ReplenishmentItem.objects.create(
            replenishment=self.client_order, product=component,
            quantity=1, unit_price=Decimal('4000000'),
        )
        self.plain = Replenishment.objects.create(
            warehouse=warehouse, created_by=self.buyurtmachi,
        )
        ReplenishmentItem.objects.create(
            replenishment=self.plain, product=component,
            quantity=2, unit_price=Decimal('4000000'),
        )

    def _post(self, user, replenishment, action):
        self.client.force_authenticate(user)
        return self.client.post(f'/api/replenishments/{replenishment.id}/{action}/')

    def _notes(self, user):
        return Notification.objects.filter(user=user, entity='Replenishment')

    def test_plain_submit_notifies_bugalter(self):
        """Oddiy to'ldirish submit'ida bugalterga xabar tushadi."""
        self._post(self.buyurtmachi, self.plain, 'submit')
        note = self._notes(self.bugalter).get()
        self.assertIn('tekshiruvda', note.title)

    def test_sales_approve_notifies_bugalter(self):
        """Sales mijoz roziligini tasdiqlagach — bugalterga xabar."""
        self._post(self.buyurtmachi, self.client_order, 'submit')
        self._post(self.sales, self.client_order, 'approve')
        note = self._notes(self.bugalter).get()
        self.assertIn('bugalter tekshiruvi', note.title)

    def test_bugalter_approve_notifies_admin(self):
        """Bugalter tasdiqlab adminga yuborganda ADMIN xabar oladi (xato tuzatildi)."""
        self._post(self.buyurtmachi, self.client_order, 'submit')
        self._post(self.sales, self.client_order, 'approve')
        response = self._post(self.bugalter, self.client_order, 'approve')
        self.assertEqual(response.data['status'], Replenishment.Status.PENDING_ADMIN)

        note = self._notes(self.admin).get()
        self.assertIn("admin tasdig'i kutilmoqda", note.title)
        self.assertIn('Bugalter tekshirib tasdiqladi', note.message)

    def test_admin_approve_notifies_bugalter_and_creator(self):
        """Admin tasdiqlagach: bugalterga to'lov, buyurtmachiga yakuniy xabar."""
        self._post(self.buyurtmachi, self.client_order, 'submit')
        self._post(self.sales, self.client_order, 'approve')
        self._post(self.bugalter, self.client_order, 'approve')
        self._post(self.admin, self.client_order, 'approve')

        pay_note = self._notes(self.bugalter).filter(title__contains="to'lov bosqichi").get()
        self.assertIn('Admin tasdiqladi', pay_note.message)
        done_note = self._notes(self.buyurtmachi).get()
        self.assertIn("to'liq tasdiqlandi", done_note.title)
