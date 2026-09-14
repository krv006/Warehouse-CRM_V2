from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.core.models import Notification
from apps.inventory.models import Product
from apps.sales.models import Contract


class ContractChainNotificationTests(APITestCase):
    """Shartnoma zanjirida ham har bir bosqich egasi xabar oladi.

    TLD zanjiridagi xato (adminga xabar tushmasligi) shartnomada ham bor edi.
    """

    def setUp(self):
        self.sales = User.objects.create_user('sales', password='p', role=User.Role.SALES)
        self.bugalter = User.objects.create_user('bugalter', password='p', role=User.Role.BUGALTER)
        self.admin = User.objects.create_user('admin', password='p', role=User.Role.ADMIN)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        product = Product.objects.create(
            sku='ADS-1', name='adas', sale_price=Decimal('5000000'),
        )
        self.client.force_authenticate(self.sales)
        self.contract_id = self.client.post('/api/contracts/', {
            'client': self.mijoz.id,
            'items': [{'product': product.id, 'quantity': 1, 'unit_price': '5000000'}],
        }, format='json').data['id']

    def _post(self, user, action, body=None):
        self.client.force_authenticate(user)
        return self.client.post(f'/api/contracts/{self.contract_id}/{action}/', body or {})

    def _notes(self, user):
        return Notification.objects.filter(user=user, entity='Contract')

    def test_submit_notifies_bugalter(self):
        self._post(self.sales, 'submit')
        note = self._notes(self.bugalter).get()
        self.assertIn('tekshiruvga keldi', note.title)

    def test_bugalter_approve_notifies_admin(self):
        self._post(self.sales, 'submit')
        response = self._post(self.bugalter, 'approve')
        self.assertEqual(response.data['status'], Contract.Status.PENDING_ADMIN)
        note = self._notes(self.admin).get()
        self.assertIn("admin tasdig'i kutilmoqda", note.title)

    def test_admin_approve_notifies_bugalter_and_sales(self):
        self._post(self.sales, 'submit')
        self._post(self.bugalter, 'approve')
        self._post(self.admin, 'approve')

        pay_note = self._notes(self.bugalter).filter(
            title__contains='pul kutilmoqda',
        ).get()
        self.assertIn("Oldindan to'lov", pay_note.message)
        sales_note = self._notes(self.sales).get()
        self.assertIn('tasdiqlandi', sales_note.title)

    def test_reject_notifies_sales(self):
        self._post(self.sales, 'submit')
        self._post(self.bugalter, 'reject', {'comment': 'Narxlar aniqlashtirilsin'})
        note = self._notes(self.sales).get()
        self.assertIn('qaytarildi', note.title)
        self.assertEqual(note.message, 'Narxlar aniqlashtirilsin')
