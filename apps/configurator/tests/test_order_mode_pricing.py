from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.configurator.models import Configuration, ConfigurationItem
from apps.core.models import Notification
from apps.inventory.models import Product
from apps.procurement.models import PriceRequest
from apps.procurement.services import answer_price_request_line
from apps.sales.models import Contract


class OrderModePricingTests(APITestCase):
    """26-§1: `order` rejimida shartnoma so'ralmagan narx bilan tuzilmasin.

    Zanjir: yangi model `order`da ishga olinadi, tarkib spetsifikatsiya
    sifatida yoziladi, lekin modelning O'Z narxi kelmaguncha submit/finalize
    to'siladi va shartnoma ochilmaydi.
    """

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.buyurtmachi = User.objects.create_user('buy', password='p', role=User.Role.SUPPLIER)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.base = Product.objects.create(
            sku='HP-990', name='HP 990', kind=Product.Kind.MACHINE,
        )
        self.ram = Product.objects.create(sku='RAM-16', name='RAM 16', kind=Product.Kind.COMPONENT)

    def _take(self):
        self.client.force_authenticate(self.sales)
        request_id = self.client.post('/api/configuration-requests/', {
            'text': '1 ta HP 990', 'base_product': self.base.id,
            'client': self.mijoz.id, 'quantity': 1,
        }, format='json').data['id']
        self.client.force_authenticate(self.engineer)
        response = self.client.post(
            f'/api/configuration-requests/{request_id}/take/',
        )
        self.assertEqual(response.status_code, 200, response.data)
        configuration = Configuration.objects.get(pk=response.data['configuration'])
        self.assertEqual(configuration.mode, Configuration.Mode.ORDER)
        # `submit` bo'sh tarkibni bloklaydi (bugungidek) — `order`da qatorlar
        # SPETSIFIKATSIYA (narxi so'ralmaydi), lekin bo'sh bo'lmasligi kerak
        ConfigurationItem.objects.create(
            configuration=configuration, component=self.ram, label='RAM', quantity=1,
        )
        return configuration

    def test_new_model_defaults_to_order_with_no_price(self):
        configuration = self._take()
        self.assertEqual(configuration.total_price, 0)
        self.assertTrue(configuration.needs_base_price)

    def test_submit_blocked_when_base_price_missing(self):
        configuration = self._take()
        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configurations/{configuration.id}/submit/')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('narxi', str(response.data))
        configuration.refresh_from_db()
        self.assertEqual(configuration.status, Configuration.Status.DRAFT)

    def test_deal_submit_blocked_with_needs_price_reason(self):
        self.client.force_authenticate(self.sales)
        request_id = self.client.post('/api/configuration-requests/', {
            'text': '1 ta HP 990', 'base_product': self.base.id,
            'client': self.mijoz.id, 'quantity': 1,
        }, format='json').data['id']
        self.client.force_authenticate(self.engineer)
        take_response = self.client.post(f'/api/configuration-requests/{request_id}/take/')
        configuration = Configuration.objects.get(pk=take_response.data['configuration'])
        ConfigurationItem.objects.create(
            configuration=configuration, component=self.ram, label='RAM', quantity=1,
        )
        response = self.client.post(
            f'/api/configuration-requests/{request_id}/submit/',
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(response.data['blocked'][0]['reason'], 'needs_price')

    def test_request_prices_opens_a_price_request_targeting_the_model(self):
        """28-§1: so'rov endi BITTA hujjat — mahsulot kartasidagi tarqoq
        eslatma emas, `PriceRequest` qatori bazaviy modelga ishora qiladi."""
        configuration = self._take()
        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configurations/{configuration.id}/request-prices/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['requested'], [self.base.name])

        price_request = PriceRequest.objects.get(pk=response.data['price_request'])
        line = price_request.lines.get()
        self.assertEqual(line.product, self.base)
        self.assertFalse(line.is_imported)

        note = Notification.objects.get(
            user=self.buyurtmachi, entity='PriceRequest', object_id=str(price_request.id),
        )
        self.assertIn('Tannarx kerak', note.title)

    def test_price_arrived_resumes_chain_and_total_price_follows_model(self):
        configuration = self._take()
        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configurations/{configuration.id}/request-prices/')
        price_request = PriceRequest.objects.get(pk=response.data['price_request'])
        line = price_request.lines.get()

        answer_price_request_line(line, self.buyurtmachi, cost_price=Decimal('18000000'))

        configuration.refresh_from_db()
        self.assertFalse(configuration.needs_base_price)
        self.assertEqual(configuration.total_price, Decimal('18000000'))
        # Buyurtmachining "narx kerak" eslatmasi yopilgan
        self.assertFalse(
            Notification.objects.filter(
                user=self.buyurtmachi, entity='PriceRequest',
                object_id=str(price_request.id), is_read=False,
            ).exists(),
        )
        # Sales'ga "narx keldi" xabari ketgan
        self.assertTrue(
            Notification.objects.filter(
                user=self.sales, entity='Configuration', object_id=str(configuration.pk),
            ).exists(),
        )

    def test_full_chain_opens_contract_with_model_price_not_zero(self):
        configuration = self._take()
        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configurations/{configuration.id}/request-prices/')
        price_request = PriceRequest.objects.get(pk=response.data['price_request'])
        answer_price_request_line(price_request.lines.get(), self.buyurtmachi, cost_price=Decimal('18000000'))

        response = self.client.post(f'/api/configurations/{configuration.id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)

        self.client.force_authenticate(self.sales)
        response = self.client.post(f'/api/configurations/{configuration.id}/approve/')
        self.assertEqual(response.status_code, 200, response.data)

        contract = Contract.objects.get()
        item = contract.items.get()
        self.assertEqual(item.unit_price, Decimal('18000000'))
        self.assertEqual(contract.total_amount, item.total_with_vat)

    def test_order_mode_with_existing_price_is_not_blocked(self):
        priced_base = Product.objects.create(
            sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE,
            sale_price=Decimal('12000000'),
        )
        self.client.force_authenticate(self.sales)
        request_id = self.client.post('/api/configuration-requests/', {
            'text': '1 ta HP 880', 'base_product': priced_base.id,
            'client': self.mijoz.id, 'quantity': 1,
        }, format='json').data['id']
        self.client.force_authenticate(self.engineer)
        take_response = self.client.post(
            f'/api/configuration-requests/{request_id}/take/', {'mode': 'order'}, format='json',
        )
        configuration = Configuration.objects.get(pk=take_response.data['configuration'])
        self.assertFalse(configuration.needs_base_price)
        ConfigurationItem.objects.create(
            configuration=configuration, component=self.ram, label='RAM', quantity=1,
        )

        response = self.client.post(f'/api/configurations/{configuration.id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)

    def test_finalize_blocked_without_base_price(self):
        from datetime import date

        from apps.configurator.models import Act

        configuration = self._take()
        configuration.status = Configuration.Status.APPROVED
        configuration.save()
        act = Act.objects.create(
            number='ACT-100', title='HP 990', issued_at=date.today(), created_by=self.engineer,
        )
        self.client.force_authenticate(self.engineer)
        response = self.client.post(
            f'/api/configurations/{configuration.id}/finalize/', {'act': act.id}, format='json',
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('narxi', str(response.data))


class OrderModePricingRegressionTests(APITestCase):
    """26-§1 case 5/6: `build`/`modify` — narx nazorati o'zgarmaydi."""

    def setUp(self):
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)

    def test_build_mode_still_blocks_on_priceless_component(self):
        from apps.configurator.models import Configuration, ConfigurationItem
        from apps.inventory.models import Warehouse
        from apps.configurator.services import submit_configuration
        from rest_framework.exceptions import ValidationError

        warehouse = Warehouse.objects.create(name='Asosiy ombor')
        base = Product.objects.create(sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE)
        part = Product.objects.create(sku='RAM-1', name='RAM', kind=Product.Kind.COMPONENT)
        configuration = Configuration.objects.create(
            base_product=base, warehouse=warehouse, created_by=self.engineer,
            mode=Configuration.Mode.BUILD,
        )
        ConfigurationItem.objects.create(
            configuration=configuration, component=part, label='RAM', quantity=1,
        )
        with self.assertRaises(ValidationError):
            submit_configuration(configuration, self.engineer)
