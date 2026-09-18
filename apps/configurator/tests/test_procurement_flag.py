from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.configurator.models import Configuration, ConfigurationItem
from apps.inventory.models import Product, Warehouse
from apps.procurement.models import Replenishment


class ProcurementFlagTests(APITestCase):
    """Konfiguratsiya buyurtmachiga yuborilgani front'ga ko'rinishi kerak.

    `procurement` (oxirgi TLD holati) va `sent_to_procurement` (ochiq hisob
    bormi) maydonlari — badge/flag shu yerdan olinadi.
    """

    def setUp(self):
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.base = Product.objects.create(
            sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE,
        )
        self.cpu = Product.objects.create(
            sku='CORE-I9', name='CORE I9', kind=Product.Kind.COMPONENT,
            cost_price=Decimal('3000000'),
        )
        self.configuration = Configuration.objects.create(
            base_product=self.base, warehouse=self.warehouse, created_by=self.engineer,
            # #4: ta'minot faqat sales tasdiqlagan yechim uchun
            status=Configuration.Status.APPROVED,
        )
        ConfigurationItem.objects.create(
            configuration=self.configuration, component=self.cpu,
            label='CPU', quantity=1,
        )
        # YANGI OQIM B4: ta'minot faqat to'langan (active) shartnoma bilan
        from apps.clients.models import Client
        from apps.sales.models import Contract

        mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        Contract.objects.create(
            client=mijoz, configuration=self.configuration,
            status=Contract.Status.ACTIVE, total_amount=Decimal('1000000'),
            created_by=self.engineer,
        )
        self.client.force_authenticate(self.engineer)

    def _detail(self):
        return self.client.get(f'/api/configurations/{self.configuration.id}/').data

    def _send(self):
        return self.client.post(
            f'/api/configurations/{self.configuration.id}/request-procurement/',
        )

    def test_not_sent_yet(self):
        """Yuborilmagan konfiguratsiyada flag false, procurement null."""
        data = self._detail()
        self.assertIsNone(data['procurement'])
        self.assertFalse(data['sent_to_procurement'])

    def test_flag_appears_after_sending(self):
        """Yuborilgach detail'da TLD raqami va holati ko'rinadi."""
        response = self._send()
        self.assertEqual(response.status_code, 201, response.data)

        data = self._detail()
        self.assertTrue(data['sent_to_procurement'])
        procurement = data['procurement']
        self.assertEqual(procurement['number'], response.data['number'])
        self.assertEqual(procurement['status'], Replenishment.Status.DRAFT)
        self.assertEqual(procurement['status_display'], 'Qoralama')
        self.assertTrue(procurement['is_open'])

    def test_second_send_is_blocked(self):
        """Tugma ikki marta bosilsa ikkinchi TLD ochilmaydi (400)."""
        self._send()
        response = self._send()
        self.assertEqual(response.status_code, 400)
        self.assertIn('allaqachon ochilgan', response.data['detail'])
        self.assertEqual(Replenishment.objects.count(), 1)

    def test_cancelled_replenishment_frees_the_flag(self):
        """Hisob bekor qilinsa flag o'chadi va yangisini yuborish mumkin."""
        self._send()
        replenishment = Replenishment.objects.get()
        replenishment.status = Replenishment.Status.CANCELLED
        replenishment.save()

        data = self._detail()
        self.assertFalse(data['sent_to_procurement'])
        # Oxirgi hisob tarixda qoladi — front "bekor qilingan" deb ko'rsata oladi
        self.assertEqual(data['procurement']['status'], Replenishment.Status.CANCELLED)
        self.assertFalse(data['procurement']['is_open'])

        self.assertEqual(self._send().status_code, 201)
        self.assertEqual(Replenishment.objects.count(), 2)

    def test_rejected_replenishment_stays_open(self):
        """Rad etilgan hisob yopiq emas — buyurtmachi to'g'irlab qayta yuboradi."""
        self._send()
        replenishment = Replenishment.objects.get()
        replenishment.status = Replenishment.Status.REJECTED
        replenishment.save()

        data = self._detail()
        self.assertTrue(data['sent_to_procurement'])
        self.assertTrue(data['procurement']['is_open'])
        self.assertEqual(self._send().status_code, 400)

    def test_delivered_replenishment_closes_the_flag(self):
        """Omborga kirim qilingan hisob yopiq — jarayon tugagan."""
        self._send()
        replenishment = Replenishment.objects.get()
        replenishment.status = Replenishment.Status.DELIVERED
        replenishment.save()

        data = self._detail()
        self.assertFalse(data['sent_to_procurement'])
        self.assertFalse(data['procurement']['is_open'])

    def test_flag_in_list_view(self):
        """Ro'yxatda ham bor — kartochkalarda badge chiqarish uchun."""
        self._send()
        rows = self.client.get('/api/configurations/').data['results']
        row = next(r for r in rows if r['id'] == self.configuration.id)
        self.assertTrue(row['sent_to_procurement'])
        self.assertEqual(row['procurement']['status'], Replenishment.Status.DRAFT)
