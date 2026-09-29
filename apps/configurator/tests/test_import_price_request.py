from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.configurator.models import Configuration, ConfigurationItem, ConfigurationRequest
from apps.inventory.models import Product
from apps.procurement.models import ImportCostSheet


class ImportPriceRequestBranchTests(APITestCase):
    """24-§6.2/§8.1: narxsiz IMPORT qator — buyurtmachiga oddiy eslatma
    o'rniga `ImportCostSheet` ochiladi."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.supplier = User.objects.create_user('buy', password='p', role=User.Role.SUPPLIER)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.base = Product.objects.create(sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE)

    def _take_config(self, quantity=1):
        self.client.force_authenticate(self.sales)
        request_id = self.client.post('/api/configuration-requests/', {
            'text': f'{quantity} ta HP 880', 'base_product': self.base.id,
            'client': self.mijoz.id, 'quantity': quantity,
        }, format='json').data['id']
        self.client.force_authenticate(self.engineer)
        # 25-§6: `self.base`da na tarkib, na qoldiq bor — `mode` berilmasa
        # endi avtomatik `order` tanlanardi; bu test import-narx OQIMINI
        # (mode tanlovini emas) tekshiradi, shuning uchun `build` aniq beriladi.
        response = self.client.post(
            f'/api/configuration-requests/{request_id}/take/',
            {'mode': 'build'}, format='json',
        )
        return Configuration.objects.get(pk=response.data['configuration'])

    def test_already_flagged_imported_component_opens_sheet_not_supplier_note(self):
        from apps.core.models import Notification

        imported_part = Product.objects.create(
            sku='CHIP-1', name='Chip', kind=Product.Kind.COMPONENT, is_imported=True,
        )
        configuration = self._take_config(quantity=3)
        ConfigurationItem.objects.create(
            configuration=configuration, component=imported_part, label='Chip', quantity=2,
        )
        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configurations/{configuration.id}/request-prices/')
        self.assertEqual(response.status_code, 200, response.data)

        sheet = ImportCostSheet.objects.get(product=imported_part)
        self.assertEqual(sheet.configuration_id, configuration.id)
        # 2 dona/qatordan x 3 partiya = 6
        self.assertEqual(sheet.quantity, 6)
        self.assertFalse(
            Notification.objects.filter(entity='Product', object_id=str(imported_part.pk)).exists(),
        )

    def test_first_time_marks_product_as_imported_via_flag(self):
        """§8.1: bayroq birinchi marta shu chaqiruvda beriladi."""
        local_part = Product.objects.create(
            sku='LOCAL-1', name='Kabel', kind=Product.Kind.COMPONENT,
        )
        configuration = self._take_config()
        ConfigurationItem.objects.create(
            configuration=configuration, component=local_part, label='Kabel', quantity=1,
        )
        self.client.force_authenticate(self.engineer)
        response = self.client.post(
            f'/api/configurations/{configuration.id}/request-prices/',
            {'imported_products': [local_part.id]}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)

        local_part.refresh_from_db()
        self.assertTrue(local_part.is_imported)
        self.assertTrue(ImportCostSheet.objects.filter(product=local_part).exists())

    def test_forgotten_flag_still_uses_old_supplier_path(self):
        """§7 case 20: bayroq unutildi — eski yo'l ishlaydi, regressiya yo'q."""
        from apps.core.models import Notification

        local_part = Product.objects.create(
            sku='LOCAL-2', name='Vint', kind=Product.Kind.COMPONENT,
        )
        configuration = self._take_config()
        ConfigurationItem.objects.create(
            configuration=configuration, component=local_part, label='Vint', quantity=1,
        )
        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configurations/{configuration.id}/request-prices/')
        self.assertEqual(response.status_code, 200, response.data)

        self.assertFalse(ImportCostSheet.objects.filter(product=local_part).exists())
        self.assertTrue(
            Notification.objects.filter(
                user=self.supplier, entity='Product', object_id=str(local_part.pk),
            ).exists(),
        )

    def test_non_imported_and_imported_components_mixed(self):
        local_part = Product.objects.create(sku='LOCAL-3', name='Kartuş', kind=Product.Kind.COMPONENT)
        imported_part = Product.objects.create(
            sku='CHIP-2', name='Chip2', kind=Product.Kind.COMPONENT, is_imported=True,
        )
        configuration = self._take_config()
        ConfigurationItem.objects.create(
            configuration=configuration, component=local_part, label='Kartuş', quantity=1,
        )
        ConfigurationItem.objects.create(
            configuration=configuration, component=imported_part, label='Chip', quantity=1,
        )
        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configurations/{configuration.id}/request-prices/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(set(response.data['requested']), {'Kartuş', 'Chip2'})
        self.assertTrue(ImportCostSheet.objects.filter(product=imported_part).exists())
        self.assertFalse(ImportCostSheet.objects.filter(product=local_part).exists())

    def test_engineer_queue_shows_only_price_asked_fact_not_amount(self):
        """§4.1: engineer navbatida summa ko'rinmaydi, faqat fakt."""
        imported_part = Product.objects.create(
            sku='CHIP-3', name='Chip3', kind=Product.Kind.COMPONENT, is_imported=True,
        )
        configuration = self._take_config()
        ConfigurationItem.objects.create(
            configuration=configuration, component=imported_part, label='Chip', quantity=1,
        )
        self.client.force_authenticate(self.engineer)
        self.client.post(f'/api/configurations/{configuration.id}/request-prices/')
        response = self.client.get(f'/api/configurations/{configuration.id}/')
        self.assertNotIn('landed_total', str(response.data))
        self.assertNotIn('unit_cost', str(response.data))
