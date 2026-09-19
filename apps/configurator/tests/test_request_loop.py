from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.configurator.models import (
    Configuration,
    ConfigurationRequest,
    ConfigurationRequestEvent,
)
from apps.core.models import Notification
from apps.inventory.models import (
    Product,
    ProductSpec,
    StockMovement,
    StockReservation,
    Warehouse,
)
from apps.inventory.services import apply_movement


class RequestLoopTests(APITestCase):
    """B15 (§2.1 aylanmasi): engineer qaytaradi, sales tuzatib qayta yuboradi."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.sales2 = User.objects.create_user('sal2', password='p', role=User.Role.SALES)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.engineer2 = User.objects.create_user('eng2', password='p', role=User.Role.ENGINEER)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.base = Product.objects.create(
            sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE,
        )
        self.ram = Product.objects.create(
            sku='RAM-16', name='RAM 16', kind=Product.Kind.COMPONENT,
            sale_price=Decimal('700000'),
        )
        ProductSpec.objects.create(
            product=self.base, component=self.ram, label='RAM', quantity=1,
        )
        apply_movement(
            product=self.ram, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('10'),
        )

    def _request(self):
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/configuration-requests/', {
            'text': 'HP 880 kerak', 'base_product': self.base.id,
            'client': self.mijoz.id, 'quantity': 2,
        }, format='json')
        return ConfigurationRequest.objects.get(pk=response.data['id'])

    def test_reject_requires_comment(self):
        request_obj = self._request()
        self.client.force_authenticate(self.engineer)
        response = self.client.post(
            f'/api/configuration-requests/{request_obj.id}/reject/', {}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('comment', response.data)

    def test_reject_new_goes_to_sales_and_leaves_pool(self):
        """`returned` — faqat sales'da: hovuzdan chiqadi, izoh bilan xabar boradi."""
        request_obj = self._request()
        self.client.force_authenticate(self.engineer)
        response = self.client.post(
            f'/api/configuration-requests/{request_obj.id}/reject/',
            {'comment': 'Model eskirgan — boshqa baza tanlang'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], ConfigurationRequest.Status.RETURNED)

        # Sales izohli xabar oladi
        note = Notification.objects.get(user=self.sales, entity='ConfigurationRequest')
        self.assertIn('qaytarildi', note.title)
        self.assertIn('eskirgan', note.message)

        # Boshqa engineer hovuzida ko'rinmaydi, sales o'zinikida ko'radi
        self.client.force_authenticate(self.engineer2)
        numbers = [r['number'] for r in self.client.get('/api/configuration-requests/').data['results']]
        self.assertNotIn(request_obj.number, numbers)
        self.client.force_authenticate(self.sales)
        numbers = [r['number'] for r in self.client.get('/api/configuration-requests/').data['results']]
        self.assertIn(request_obj.number, numbers)

    def test_reject_in_progress_is_400(self):
        """9-to'plam §1: ishga olingan zayavka QAYTARILMAYDI — ask-sales/release bor."""
        request_obj = self._request()
        self.client.force_authenticate(self.engineer)
        take = self.client.post(f'/api/configuration-requests/{request_obj.id}/take/')
        configuration = Configuration.objects.get(pk=take.data['configuration'])

        response = self.client.post(
            f'/api/configuration-requests/{request_obj.id}/reject/',
            {'comment': 'Tarkib mantiqsiz'}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('ask-sales', str(response.data['detail']))
        configuration.refresh_from_db()
        # Engineer'ning ishi TEGILMAGAN
        self.assertEqual(configuration.status, Configuration.Status.DRAFT)

    def test_release_returns_to_pool_and_cancels_configuration(self):
        """9-to'plam §2: vaqti yo'q — ish hovuzga (`new`), CFG bekor, bron bo'sh."""
        request_obj = self._request()
        self.client.force_authenticate(self.engineer)
        take = self.client.post(f'/api/configuration-requests/{request_obj.id}/take/')
        configuration = Configuration.objects.get(pk=take.data['configuration'])
        self.assertTrue(
            StockReservation.objects.filter(
                configuration=configuration,
                status=StockReservation.Status.ACTIVE,
            ).exists(),
        )
        # Boshqa engineer birovning ishini qaytara olmaydi
        self.client.force_authenticate(self.engineer2)
        response = self.client.post(
            f'/api/configuration-requests/{request_obj.id}/release/',
            {'comment': 'x'}, format='json',
        )
        # Birovning ishi uning ro'yxatida ham yo'q (404) — taqiq kafolatlangan
        self.assertIn(response.status_code, (403, 404))

        Notification.objects.all().delete()
        self.client.force_authenticate(self.engineer)
        response = self.client.post(
            f'/api/configuration-requests/{request_obj.id}/release/',
            {'comment': 'Vaqtim yo\'q'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], ConfigurationRequest.Status.NEW)

        configuration.refresh_from_db()
        request_obj.refresh_from_db()
        self.assertEqual(configuration.status, Configuration.Status.CANCELLED)
        self.assertEqual(configuration.cancel_reason, 'Vaqtim yo\'q')
        self.assertIsNone(request_obj.taken_by)
        self.assertFalse(
            StockReservation.objects.filter(
                configuration=configuration,
                status=StockReservation.Status.ACTIVE,
            ).exists(),
        )
        # Hovuz xabar oladi (o'ziga emas), sales INFO oladi
        self.assertTrue(Notification.objects.filter(user=self.engineer2).exists())
        self.assertFalse(
            Notification.objects.filter(
                user=self.engineer, entity='ConfigurationRequest',
            ).exists(),
        )
        self.assertTrue(Notification.objects.filter(user=self.sales).exists())
        # Boshqa engineer qayta oladi — toza chernovik ochiladi
        self.client.force_authenticate(self.engineer2)
        response = self.client.post(f'/api/configuration-requests/{request_obj.id}/take/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotEqual(response.data['configuration'], configuration.pk)

    def test_ask_sales_and_answer_loop_keeps_work(self):
        """9-to'plam §1B: savol-javob — tarkib ham, bron ham joyida qoladi."""
        request_obj = self._request()
        self.client.force_authenticate(self.engineer)
        take = self.client.post(f'/api/configuration-requests/{request_obj.id}/take/')
        configuration = Configuration.objects.get(pk=take.data['configuration'])

        # Izohsiz savol 400
        response = self.client.post(
            f'/api/configurations/{configuration.id}/ask-sales/', {}, format='json',
        )
        self.assertEqual(response.status_code, 400)

        response = self.client.post(
            f'/api/configurations/{configuration.id}/ask-sales/',
            {'comment': 'RAM 32 kerakmi yoki 64?'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            response.data['status'], Configuration.Status.PENDING_CLARIFICATION,
        )
        # Bron joyida qoladi — mol o'sha-o'sha kerak
        self.assertTrue(
            StockReservation.objects.filter(
                configuration=configuration,
                status=StockReservation.Status.ACTIVE,
            ).exists(),
        )
        # Zayavka egasi savolni oladi
        note = Notification.objects.get(user=self.sales, entity='Configuration')
        self.assertIn('savol', note.title)

        # Engineer o'zi javob bera olmaydi, sales javob beradi
        response = self.client.post(
            f'/api/configurations/{configuration.id}/answer/',
            {'comment': '64 qilaylik'}, format='json',
        )
        self.assertEqual(response.status_code, 403)
        self.client.force_authenticate(self.sales)
        response = self.client.post(
            f'/api/configurations/{configuration.id}/answer/',
            {'comment': '64 qilaylik'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], Configuration.Status.DRAFT)

        # Suhbat tarixda: savol -> javob (mavjud approvals ro'yxatida)
        decisions = [a['decision'] for a in response.data['approvals']]
        self.assertEqual(decisions, ['question', 'answer'])
        # Engineer javob xabarini oldi va ishni davom ettiradi (submit ochiq)
        self.assertTrue(
            Notification.objects.filter(
                user=self.engineer, title__contains='javob',
            ).exists(),
        )
        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configurations/{configuration.id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)

    def test_resend_returns_to_pool(self):
        """Sales tuzatib qayta yuboradi: `returned` → `new`, engineerlar xabar oladi."""
        request_obj = self._request()
        self.client.force_authenticate(self.engineer)
        self.client.post(
            f'/api/configuration-requests/{request_obj.id}/reject/',
            {'comment': 'Tuzating'}, format='json',
        )
        # Boshqa sales qayta yubora olmaydi
        self.client.force_authenticate(self.sales2)
        self.assertEqual(
            self.client.post(
                f'/api/configuration-requests/{request_obj.id}/resend/',
            ).status_code,
            404,  # o'z ro'yxatida yo'q — ko'rmaydi ham
        )
        Notification.objects.all().delete()
        self.client.force_authenticate(self.sales)
        response = self.client.post(
            f'/api/configuration-requests/{request_obj.id}/resend/',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], ConfigurationRequest.Status.NEW)
        self.assertTrue(Notification.objects.filter(user=self.engineer).exists())

    def test_events_keep_the_loop_history(self):
        """Aylanma tarixda: created → returned → resent → taken → released."""
        request_obj = self._request()
        self.client.force_authenticate(self.engineer)
        self.client.post(
            f'/api/configuration-requests/{request_obj.id}/reject/',
            {'comment': 'Model tanlanmagan'}, format='json',
        )
        self.client.force_authenticate(self.sales)
        self.client.post(f'/api/configuration-requests/{request_obj.id}/resend/')
        self.client.force_authenticate(self.engineer)
        self.client.post(f'/api/configuration-requests/{request_obj.id}/take/')
        response = self.client.post(
            f'/api/configuration-requests/{request_obj.id}/release/',
            {'comment': 'Vaqtim yo\'q'}, format='json',
        )
        stages = [e['stage'] for e in response.data['events']]
        self.assertEqual(stages, [
            ConfigurationRequestEvent.Stage.CREATED,
            ConfigurationRequestEvent.Stage.RETURNED,
            ConfigurationRequestEvent.Stage.RESENT,
            ConfigurationRequestEvent.Stage.TAKEN,
            ConfigurationRequestEvent.Stage.RELEASED,
        ])
