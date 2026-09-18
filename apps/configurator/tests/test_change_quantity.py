from decimal import Decimal

from django.utils.timezone import now

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.configurator.models import Configuration, ConfigurationRequest
from apps.core.models import Notification
from apps.inventory.models import (
    Product,
    ProductSpec,
    StockMovement,
    StockReservation,
    Warehouse,
)
from apps.inventory.services import apply_movement
from apps.procurement.models import Replenishment


class ChangeQuantityTests(APITestCase):
    """4-to'plam §2: mijoz partiya sonini o'zgartirsa zanjir qaytadan boshlanmaydi."""

    def setUp(self):
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        User.objects.create_user('buy', password='p', role=User.Role.SUPPLIER)
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        from apps.clients.models import Client

        # YANGI OQIM B10: approve mijozsiz o'tmaydi — shartnoma ochiladi
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
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

    def _stock_in(self, product, quantity):
        apply_movement(
            product=product, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal(quantity),
        )

    def _approved_config(self, quantity=10):
        """ZVK -> take -> submit -> sales approve zanjiri orqali."""
        self.client.force_authenticate(self.sales)
        request_id = self.client.post('/api/configuration-requests/', {
            'text': f'{quantity} ta HP 880', 'base_product': self.base.id,
            'quantity': quantity, 'client': self.mijoz.id,
        }, format='json').data['id']
        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configuration-requests/{request_id}/take/')
        configuration = Configuration.objects.get(pk=response.data['configuration'])
        self.client.post(f'/api/configurations/{configuration.id}/submit/')
        self.client.force_authenticate(self.sales)
        self.client.post(f'/api/configurations/{configuration.id}/approve/')
        self.client.force_authenticate(self.engineer)
        configuration.refresh_from_db()
        return configuration

    def _change(self, configuration, quantity, comment='Mijoz sonni o\'zgartirdi'):
        return self.client.post(
            f'/api/configurations/{configuration.id}/change-quantity/',
            {'quantity': quantity, 'comment': comment}, format='json',
        )

    def test_approved_updates_everything_and_returns_to_sales(self):
        """10 -> 100: son, bron, holat, zayavka soni — hammasi birga o'zgaradi."""
        self._stock_in(self.ram, 150)
        configuration = self._approved_config(quantity=10)
        Notification.objects.all().delete()

        response = self._change(configuration, 100)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['quantity'], 100)
        self.assertEqual(response.data['status'], Configuration.Status.PENDING_SALES)

        # Bron yangi partiyaga mos: RAM x100 (omborda 150 bor)
        reservation = StockReservation.objects.get(
            configuration=configuration,
            status=StockReservation.Status.ACTIVE,
        )
        self.assertEqual(reservation.quantity, Decimal('100'))

        # Zayavka soni ergashdi — ikki hujjatda bir xil son
        request_obj = ConfigurationRequest.objects.get()
        self.assertEqual(request_obj.quantity, 100)

        # Zayavka egasi (sales) qayta tasdiqlash haqida xabar oldi
        note = Notification.objects.get(user=self.sales)
        self.assertIn('10 → 100', note.title)
        self.assertIn('qayta tasdiqlang', note.message)

    def test_assembled_configuration_rejected(self):
        """Mahsulot yig'ilgan — ombor harakatlari yozilgan, partiya o'zgarmaydi."""
        self._stock_in(self.ram, 150)
        configuration = self._approved_config()
        configuration.assembled_at = now()
        configuration.save()
        response = self._change(configuration, 100)
        self.assertEqual(response.status_code, 400)
        configuration.refresh_from_db()
        self.assertEqual(configuration.quantity, 10)

    def test_open_tld_beyond_draft_rejected_with_number(self):
        """TLD chernovikdan o'tgan — mol yo'lda, xabar TLD raqamini aytadi."""
        configuration = self._approved_config()  # RAM omborda yo'q
        self.client.post(
            f'/api/configurations/{configuration.id}/request-procurement/',
        )
        replenishment = Replenishment.objects.get()
        replenishment.status = Replenishment.Status.PENDING_BUGALTER
        replenishment.save()

        response = self._change(configuration, 100)
        self.assertEqual(response.status_code, 400)
        self.assertIn(replenishment.number, str(response.data['detail']))
        self.assertEqual(int(response.data['replenishment']), replenishment.pk)

    def test_open_draft_tld_allowed_and_supplier_notified(self):
        """Chernovik TLD to'smaydi — buyurtmachi qatorlarni o'zi moslaydi."""
        configuration = self._approved_config()
        self.client.post(
            f'/api/configurations/{configuration.id}/request-procurement/',
        )
        replenishment = Replenishment.objects.get()
        Notification.objects.all().delete()

        response = self._change(configuration, 100)
        self.assertEqual(response.status_code, 200, response.data)
        supplier = User.objects.get(username='buy')
        note = Notification.objects.get(user=supplier)
        self.assertIn(replenishment.number, note.title)

    def test_sales_cannot_change(self):
        """Sales so'raydi, engineer yozadi (§3.4 egalik) — sales'ga 403."""
        self._stock_in(self.ram, 150)
        configuration = self._approved_config()
        self.client.force_authenticate(self.sales)
        response = self._change(configuration, 100)
        self.assertEqual(response.status_code, 403)

    def test_invalid_quantity_rejected(self):
        self._stock_in(self.ram, 150)
        configuration = self._approved_config()
        for value in (0, -5, 'abc', 10):  # 10 — o'zgarmagan son ham rad
            response = self._change(configuration, value)
            self.assertEqual(response.status_code, 400, value)
        configuration.refresh_from_db()
        self.assertEqual(configuration.quantity, 10)
        self.assertEqual(configuration.status, Configuration.Status.APPROVED)
