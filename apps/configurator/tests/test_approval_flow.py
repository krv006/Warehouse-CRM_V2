from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.configurator.models import Configuration, ConfigurationItem, ConfigurationRequest
from apps.core.models import Notification
from apps.inventory.models import Product, StockMovement, Warehouse
from apps.inventory.services import apply_movement


class ApprovalFlowExtrasTests(APITestCase):
    """#4 qo'shimchalari: navbat, kirim xabari, ACT taklifi."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.buyurtmachi = User.objects.create_user('buy', password='p', role=User.Role.SUPPLIER)
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.base = Product.objects.create(
            sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE,
        )
        self.ssd = Product.objects.create(
            sku='SSD-1TB', name='SSD 1 TB', kind=Product.Kind.COMPONENT,
            sale_price=Decimal('1500000'),
        )
        self.configuration = Configuration.objects.create(
            base_product=self.base, warehouse=self.warehouse, created_by=self.engineer,
        )
        ConfigurationItem.objects.create(
            configuration=self.configuration, component=self.ssd,
            label='SSD', quantity=1,
        )
        ConfigurationRequest.objects.create(
            text='HP 880', created_by=self.sales, configuration=self.configuration,
            status=ConfigurationRequest.Status.IN_PROGRESS, taken_by=self.engineer,
        )

    def test_sales_queue_shows_configuration_review(self):
        """my-work: sales ko'rigidagi konfiguratsiya navbatga tushadi."""
        self.client.force_authenticate(self.engineer)
        self.client.post(f'/api/configurations/{self.configuration.id}/submit/')

        self.client.force_authenticate(self.sales)
        work = self.client.get('/api/my-work/').data
        row = next(r for r in work['items'] if r['section'] == 'configurations')
        self.assertEqual(row['reason'], 'configuration_review')
        self.assertEqual(work['counts']['configurations'], 1)

    def test_procurement_blocked_until_approved(self):
        """#4-Q2: ta'minot tasdiqdan OLDIN ishlamaydi — mol behuda olinmasin."""
        self.client.force_authenticate(self.engineer)
        response = self.client.post(
            f'/api/configurations/{self.configuration.id}/request-procurement/',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('tasdiqlansin', str(response.data))

    def test_receive_notifies_engineer_goods_arrived(self):
        """#4C: mol kelganda yig'adigan odam (engineer) xabar oladi."""
        self.configuration.status = Configuration.Status.APPROVED
        self.configuration.save()
        self.client.force_authenticate(self.engineer)
        response = self.client.post(
            f'/api/configurations/{self.configuration.id}/request-procurement/',
        )
        self.assertEqual(response.status_code, 201, response.data)

        from apps.procurement.models import Replenishment

        replenishment = Replenishment.objects.get()
        Replenishment.objects.filter(pk=replenishment.pk).update(
            status=Replenishment.Status.ORDERED,
        )
        Notification.objects.all().delete()
        self.client.force_authenticate(self.buyurtmachi)
        response = self.client.post(f'/api/replenishments/{replenishment.id}/receive/')
        self.assertEqual(response.status_code, 200, response.data)

        note = Notification.objects.get(user=self.engineer, entity='Configuration')
        self.assertIn('mol keldi', note.title)

    def test_assemble_returns_act_suggestion(self):
        """#4D: ACT matni bajarilgan ishdan avtomatik taklif qilinadi."""
        self.configuration.status = Configuration.Status.APPROVED
        self.configuration.save()
        apply_movement(
            product=self.ssd, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('3'),
        )
        self.client.force_authenticate(self.engineer)
        response = self.client.post(
            f'/api/configurations/{self.configuration.id}/assemble/',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn('HP 880', response.data['act_suggestion'])
        self.assertIn('SSD 1 TB', response.data['act_suggestion'])

    def test_editing_locked_while_pending_sales(self):
        """Ko'rikdagi konfiguratsiya tahrirlanmaydi — reject qaytargachgina ochiladi."""
        self.client.force_authenticate(self.engineer)
        self.client.post(f'/api/configurations/{self.configuration.id}/submit/')
        response = self.client.patch(
            f'/api/configurations/{self.configuration.id}/', {'note': 'x'}, format='json',
        )
        self.assertEqual(response.status_code, 400)
