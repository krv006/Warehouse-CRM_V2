from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.core.models import Notification
from apps.core.services import resolve_notifications
from apps.inventory.models import Product
from apps.sales.models import Contract, ContractItem


class MarkAllReadTests(APITestCase):
    """4-to'plam §4A: hammasini bitta so'rov bilan o'qildi qilish."""

    def setUp(self):
        self.sales1 = User.objects.create_user('s1', password='p', role=User.Role.SALES)
        self.sales2 = User.objects.create_user('s2', password='p', role=User.Role.SALES)
        for user, count in ((self.sales1, 3), (self.sales2, 2)):
            for index in range(count):
                Notification.objects.create(
                    user=user, title=f'Xabar {index}', message='...',
                )

    def test_marks_only_own_and_returns_count(self):
        self.client.force_authenticate(self.sales1)
        response = self.client.post('/api/notifications/mark-all-read/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['updated'], 3)

        self.assertFalse(
            Notification.objects.filter(user=self.sales1, is_read=False).exists(),
        )
        # Birovniki tegilmagan
        self.assertEqual(
            Notification.objects.filter(user=self.sales2, is_read=False).count(), 2,
        )

    def test_second_call_updates_nothing(self):
        self.client.force_authenticate(self.sales1)
        self.client.post('/api/notifications/mark-all-read/')
        response = self.client.post('/api/notifications/mark-all-read/')
        self.assertEqual(response.data['updated'], 0)

    def test_object_id_filter_available(self):
        """§4: object_id filtri — "shu hujjat bo'yicha xabarlar" ko'rinishi."""
        Notification.objects.create(
            user=self.sales1, title='SHT', message='...',
            entity='Contract', object_id='36',
        )
        self.client.force_authenticate(self.sales1)
        response = self.client.get(
            '/api/notifications/?entity=Contract&object_id=36',
        )
        self.assertEqual(response.data['count'], 1)


class ResolveOnTransitionTests(APITestCase):
    """4-to'plam §4B: ish bitganda eslatma o'zi yopiladi — bajargan odamniki."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        User.objects.create_user('adm', password='p', role=User.Role.ADMIN)
        client_obj = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        product = Product.objects.create(sku='HP-880', name='HP 880')
        self.contract = Contract.objects.create(
            client=client_obj, total_amount=Decimal('5000000'),
            created_by=self.sales, status=Contract.Status.PENDING_BUGALTER,
        )
        ContractItem.objects.create(
            contract=self.contract, product=product, quantity=1,
            unit_price=Decimal('5000000'),
        )

    def _note(self, user):
        return Notification.objects.create(
            user=user,
            title=f'{self.contract.number}: Didoxdan qabul qiling',
            message='Sales shartnomani yubordi.',
            entity='Contract', object_id=str(self.contract.pk),
        )

    def test_approve_resolves_actors_notification_only(self):
        mine = self._note(self.bugalter)
        someone_elses = self._note(self.sales)

        self.client.force_authenticate(self.bugalter)
        response = self.client.post(
            f'/api/contracts/{self.contract.id}/approve/',
            {'didox_number': 'DDX-1'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)

        mine.refresh_from_db()
        someone_elses.refresh_from_db()
        self.assertTrue(mine.is_read)          # ish bajarildi — vazifa yopildi
        self.assertFalse(someone_elses.is_read)  # boshqa odamniki turadi

    def test_resolve_helper_counts_and_idempotent(self):
        self._note(self.bugalter)
        updated = resolve_notifications(
            'Contract', self.contract.pk, user=self.bugalter,
        )
        self.assertEqual(updated, 1)
        # Allaqachon o'qilgan — ikkinchi marta yangilanmaydi
        self.assertEqual(
            resolve_notifications('Contract', self.contract.pk, user=self.bugalter),
            0,
        )
