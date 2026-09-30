from decimal import Decimal

from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.configurator.models import Configuration, ConfigurationItem, ConfigurationRequest
from apps.core.models import Notification
from apps.inventory.models import Product
from apps.procurement.models import PriceRequest, PriceRequestLine
from apps.procurement.services import (
    answer_price_request_line,
    fill_price_request_customs,
    fill_price_request_logistics,
    mark_price_request_line_imported,
    open_price_request,
    return_price_request_line,
    send_price_request_line_to_customs,
)


class PriceRequestFlowTests(APITestCase):
    """28-§1/§6/§7: mahalliy va import qatorlar — asosiy oqim."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.logist = User.objects.create_user('log', password='p', role=User.Role.LOGIST)
        self.declarant = User.objects.create_user('dek', password='p', role=User.Role.DECLARANT)
        self.buyurtmachi = User.objects.create_user('buy', password='p', role=User.Role.SUPPLIER)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.base = Product.objects.create(sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE)

    def _take_config(self):
        self.client.force_authenticate(self.sales)
        request_id = self.client.post('/api/configuration-requests/', {
            'text': '1 ta HP 880', 'base_product': self.base.id,
            'client': self.mijoz.id, 'quantity': 1,
        }, format='json').data['id']
        self.client.force_authenticate(self.engineer)
        response = self.client.post(
            f'/api/configuration-requests/{request_id}/take/', {'mode': 'build'}, format='json',
        )
        return Configuration.objects.get(pk=response.data['configuration'])

    def test_local_component_answered_directly_by_supplier(self):
        local_part = Product.objects.create(sku='LOCAL-1', name='Kabel', kind=Product.Kind.COMPONENT)
        configuration = self._take_config()
        ConfigurationItem.objects.create(
            configuration=configuration, component=local_part, label='Kabel', quantity=1,
        )
        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configurations/{configuration.id}/request-prices/')
        self.assertEqual(response.status_code, 200, response.data)
        price_request_id = response.data['price_request']
        self.assertIsNotNone(price_request_id)

        price_request = PriceRequest.objects.get(pk=price_request_id)
        line = price_request.lines.get()
        self.assertFalse(line.is_imported)
        self.assertEqual(price_request.status, PriceRequest.Status.WAITING_SUPPLIER)

        answer_price_request_line(line, self.buyurtmachi, cost_price=Decimal('50000'))
        line.refresh_from_db()
        price_request.refresh_from_db()
        self.assertIsNotNone(line.answered_at)
        self.assertEqual(price_request.status, PriceRequest.Status.ANSWERED)
        local_part.refresh_from_db()
        self.assertEqual(local_part.cost_price, Decimal('50000'))

        # CFG davom etadi — narxsiz qator qolmadi
        configuration.refresh_from_db()
        self.assertEqual(configuration.items_without_price, [])

    def test_import_flow_no_cached_code_goes_through_logist_and_declarant(self):
        imported_part = Product.objects.create(
            sku='CHIP-1', name='Chip', kind=Product.Kind.COMPONENT, is_imported=True,
        )
        configuration = self._take_config()
        ConfigurationItem.objects.create(
            configuration=configuration, component=imported_part, label='Chip', quantity=2,
        )
        self.client.force_authenticate(self.engineer)
        self.client.post(f'/api/configurations/{configuration.id}/request-prices/')

        line = PriceRequestLine.objects.get(product=imported_part)
        self.assertTrue(line.is_imported)
        self.assertEqual(line.status, PriceRequest.Status.WAITING_LOGISTICS)
        self.assertEqual(line.request.status, PriceRequest.Status.WAITING_LOGISTICS)

        fill_price_request_logistics(line, self.logist, logistics_total=Decimal('100000'))
        line.refresh_from_db()
        self.assertEqual(line.status, PriceRequest.Status.WAITING_CUSTOMS)
        self.assertEqual(line.freight_to_border, Decimal('100000'))  # case 9: sukut — jami

        fill_price_request_customs(
            line, self.declarant, tnved_code='8471.30', duty_percent=Decimal('10'),
        )
        line.refresh_from_db()
        self.assertEqual(line.status, PriceRequest.Status.WAITING_SUPPLIER)
        self.assertFalse(line.customs_auto_filled)

        answer_price_request_line(
            line, self.buyurtmachi, currency='USD',
            goods_price=Decimal('100'), exchange_rate=Decimal('12700'),
        )
        line.refresh_from_db()
        self.assertIsNotNone(line.answered_at)
        self.assertIsNotNone(line.cost_price)

        imported_part.refresh_from_db()
        self.assertEqual(imported_part.tnved_code, '8471.30')
        self.assertEqual(imported_part.duty_percent, Decimal('10.00'))
        self.assertEqual(imported_part.cost_price, line.cost_price)

    def test_second_import_of_same_product_skips_declarant(self):
        imported_part = Product.objects.create(
            sku='CHIP-2', name='Chip2', kind=Product.Kind.COMPONENT, is_imported=True,
            tnved_code='8471.30', duty_percent=Decimal('10'),
            certificate_cost=Decimal('50000'), laboratory_cost=Decimal('20000'),
        )
        configuration = self._take_config()
        ConfigurationItem.objects.create(
            configuration=configuration, component=imported_part, label='Chip', quantity=1,
        )
        self.client.force_authenticate(self.engineer)
        self.client.post(f'/api/configurations/{configuration.id}/request-prices/')

        line = PriceRequestLine.objects.get(product=imported_part)
        self.assertTrue(line.customs_auto_filled)
        self.assertEqual(line.tnved_code, '8471.30')
        self.assertEqual(line.duty_percent, Decimal('10.00'))
        # Logistika hali kiritilmagan — status hamon waiting_logistics
        self.assertEqual(line.status, PriceRequest.Status.WAITING_LOGISTICS)

        fill_price_request_logistics(line, self.logist, logistics_total=Decimal('50000'))
        line.refresh_from_db()
        # Deklarant o'tkazib yuborildi — to'g'ridan buyurtmachi navbatiga
        self.assertEqual(line.status, PriceRequest.Status.WAITING_SUPPLIER)

    def test_supplier_can_send_auto_filled_line_back_to_customs(self):
        """§3 case 4: buyurtmachi avtomatik o'tkazilgan qatorga shubhalanadi."""
        imported_part = Product.objects.create(
            sku='CHIP-3', name='Chip3', kind=Product.Kind.COMPONENT, is_imported=True,
            tnved_code='8471.30', duty_percent=Decimal('10'),
        )
        configuration = self._take_config()
        ConfigurationItem.objects.create(
            configuration=configuration, component=imported_part, label='Chip', quantity=1,
        )
        self.client.force_authenticate(self.engineer)
        self.client.post(f'/api/configurations/{configuration.id}/request-prices/')
        line = PriceRequestLine.objects.get(product=imported_part)
        fill_price_request_logistics(line, self.logist, logistics_total=Decimal('50000'))
        line.refresh_from_db()
        self.assertEqual(line.status, PriceRequest.Status.WAITING_SUPPLIER)

        send_price_request_line_to_customs(line, self.buyurtmachi)
        line.refresh_from_db()
        self.assertFalse(line.customs_auto_filled)
        self.assertEqual(line.status, PriceRequest.Status.WAITING_CUSTOMS)

    def test_mixed_local_and_import_lines_progress_independently(self):
        """§6 case 5: har qator o'z yo'lidan; so'rov eng orqadagi qator bo'yicha."""
        local_part = Product.objects.create(sku='LOCAL-4', name='Vint', kind=Product.Kind.COMPONENT)
        imported_part = Product.objects.create(
            sku='CHIP-4', name='Chip4', kind=Product.Kind.COMPONENT, is_imported=True,
        )
        configuration = self._take_config()
        ConfigurationItem.objects.create(
            configuration=configuration, component=local_part, label='Vint', quantity=1,
        )
        ConfigurationItem.objects.create(
            configuration=configuration, component=imported_part, label='Chip', quantity=1,
        )
        self.client.force_authenticate(self.engineer)
        self.client.post(f'/api/configurations/{configuration.id}/request-prices/')

        price_request = PriceRequest.objects.get()
        local_line = price_request.lines.get(product=local_part)
        import_line = price_request.lines.get(product=imported_part)
        self.assertEqual(local_line.status, PriceRequest.Status.WAITING_SUPPLIER)
        self.assertEqual(import_line.status, PriceRequest.Status.WAITING_LOGISTICS)
        # So'rov eng ORQADAGI (import) qator bo'yicha
        self.assertEqual(price_request.status, PriceRequest.Status.WAITING_LOGISTICS)

        answer_price_request_line(local_line, self.buyurtmachi, cost_price=Decimal('10000'))
        price_request.refresh_from_db()
        # Mahalliy tugadi, import hali logist navbatida — so'rov hamon shunda
        self.assertEqual(price_request.status, PriceRequest.Status.WAITING_LOGISTICS)


class PriceRequestIsolationTests(APITestCase):
    """28-§2/§7: uch rol bir-birining raqamini ko'rmaydi."""

    def setUp(self):
        self.admin = User.objects.create_user('adm', password='p', role=User.Role.ADMIN)
        self.logist = User.objects.create_user('log', password='p', role=User.Role.LOGIST)
        self.declarant = User.objects.create_user('dek', password='p', role=User.Role.DECLARANT)
        self.buyurtmachi = User.objects.create_user('buy', password='p', role=User.Role.SUPPLIER)
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        base = Product.objects.create(sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE)
        imported_part = Product.objects.create(
            sku='CHIP-5', name='Chip5', kind=Product.Kind.COMPONENT, is_imported=True,
        )
        self.client.force_authenticate(self.sales)
        request_id = self.client.post('/api/configuration-requests/', {
            'text': '1 ta HP 880', 'base_product': base.id,
            'client': self.mijoz.id, 'quantity': 1,
        }, format='json').data['id']
        self.client.force_authenticate(self.engineer)
        take_response = self.client.post(
            f'/api/configuration-requests/{request_id}/take/', {'mode': 'build'}, format='json',
        )
        configuration = Configuration.objects.get(pk=take_response.data['configuration'])
        ConfigurationItem.objects.create(
            configuration=configuration, component=imported_part, label='Chip', quantity=1,
        )
        self.client.post(f'/api/configurations/{configuration.id}/request-prices/')
        self.line = PriceRequestLine.objects.get(product=imported_part)
        fill_price_request_logistics(self.line, self.logist, logistics_total=Decimal('100000'))
        fill_price_request_customs(self.line, self.declarant, tnved_code='8471.30', duty_percent=10)
        self.line.refresh_from_db()

    def _line_data(self, user):
        self.client.force_authenticate(user)
        response = self.client.get(f'/api/price-request-lines/{self.line.id}/')
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_logist_does_not_see_goods_or_customs_or_totals(self):
        data = self._line_data(self.logist)
        for field in ('goods_price', 'exchange_rate', 'cost_price', 'tnved_code', 'duty_percent', 'landed_total'):
            self.assertNotIn(field, data)
        self.assertIn('logistics_total', data)

    def test_declarant_does_not_see_goods_or_logistics_or_totals(self):
        data = self._line_data(self.declarant)
        for field in ('goods_price', 'exchange_rate', 'cost_price', 'logistics_total', 'freight_to_border', 'landed_total'):
            self.assertNotIn(field, data)
        self.assertIn('tnved_code', data)

    def test_supplier_sees_everything(self):
        data = self._line_data(self.buyurtmachi)
        for field in ('logistics_total', 'tnved_code', 'goods_price', 'landed_total'):
            self.assertIn(field, data)

    def test_bugalter_and_admin_see_everything(self):
        for user in (self.bugalter, self.admin):
            data = self._line_data(user)
            for field in ('logistics_total', 'tnved_code', 'goods_price', 'landed_total'):
                self.assertIn(field, data)

    def test_logist_cannot_fill_customs(self):
        self.client.force_authenticate(self.logist)
        response = self.client.post(
            f'/api/price-request-lines/{self.line.id}/fill-customs/',
            {'tnved_code': '1234.56'}, format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_declarant_cannot_fill_logistics(self):
        self.client.force_authenticate(self.declarant)
        response = self.client.post(
            f'/api/price-request-lines/{self.line.id}/fill-logistics/',
            {'logistics_total': 1000}, format='json',
        )
        self.assertEqual(response.status_code, 403)


class PriceRequestCalculationTests(APITestCase):
    """28-§2: hisob — QQS bojxona qiymatidan, invoysdan emas."""

    def setUp(self):
        self.logist = User.objects.create_user('log', password='p', role=User.Role.LOGIST)
        self.declarant = User.objects.create_user('dek', password='p', role=User.Role.DECLARANT)
        self.buyurtmachi = User.objects.create_user('buy', password='p', role=User.Role.SUPPLIER)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.product = Product.objects.create(
            sku='CHIP-6', name='Chip6', kind=Product.Kind.COMPONENT, is_imported=True,
        )
        base = Product.objects.create(sku='HP-1', name='HP 1', kind=Product.Kind.MACHINE)
        configuration = Configuration.objects.create(
            base_product=base, created_by=self.engineer, mode=Configuration.Mode.BUILD,
        )
        ConfigurationItem.objects.create(
            configuration=configuration, component=self.product, label='Chip', quantity=1,
        )
        self.price_request = open_price_request(
            configuration, self.engineer, lines=[(self.product, Decimal('1'))],
        )
        self.line = self.price_request.lines.get()

    def test_uzs_currency_forces_exchange_rate_to_one(self):
        fill_price_request_logistics(self.line, self.logist, logistics_total=Decimal('0'))
        fill_price_request_customs(self.line, self.declarant, tnved_code='1', duty_percent=0)
        self.line.refresh_from_db()
        answer_price_request_line(
            self.line, self.buyurtmachi, currency='UZS', goods_price=Decimal('500000'),
        )
        self.line.refresh_from_db()
        self.assertEqual(self.line.exchange_rate, Decimal('1'))

    def test_duty_amount_overrides_percent(self):
        fill_price_request_logistics(self.line, self.logist, logistics_total=Decimal('0'))
        fill_price_request_customs(
            self.line, self.declarant, tnved_code='1', duty_percent=50, duty_amount=Decimal('1000'),
        )
        self.line.refresh_from_db()
        self.assertEqual(self.line.duty, Decimal('1000'))

    def test_suggested_cost_matches_formula(self):
        fill_price_request_logistics(
            self.line, self.logist, logistics_total=Decimal('100000'), freight_to_border=Decimal('80000'),
        )
        fill_price_request_customs(
            self.line, self.declarant, tnved_code='1', duty_percent=Decimal('10'),
            customs_fee=Decimal('5000'),
        )
        self.line.refresh_from_db()
        self.line.goods_price = Decimal('100')
        self.line.exchange_rate = Decimal('12000')
        self.line.save()

        customs_value = Decimal('100') * Decimal('12000') + Decimal('80000')  # 1 280 000
        duty = customs_value * Decimal('10') / Decimal('100')  # 128 000
        vat = (customs_value + duty) * Decimal('12') / Decimal('100')  # 168 960
        expected_landed = (
            Decimal('100') * Decimal('12000') + Decimal('100000')
            + duty + vat + Decimal('5000')
        )
        self.assertEqual(self.line.landed_total, expected_landed)
        self.assertEqual(self.line.suggested_cost, expected_landed.quantize(Decimal('0.01')))


class PriceRequestOrderModeTests(APITestCase):
    """26-§1(c) + 28-§1: `order` rejimida narx bazaviy modelning o'zidan so'raladi."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.buyurtmachi = User.objects.create_user('buy', password='p', role=User.Role.SUPPLIER)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.base = Product.objects.create(sku='HP-990', name='HP 990', kind=Product.Kind.MACHINE)

    def test_order_mode_price_request_targets_base_product(self):
        self.client.force_authenticate(self.sales)
        request_id = self.client.post('/api/configuration-requests/', {
            'text': '1 ta HP 990', 'base_product': self.base.id,
            'client': self.mijoz.id, 'quantity': 1,
        }, format='json').data['id']
        self.client.force_authenticate(self.engineer)
        take_response = self.client.post(f'/api/configuration-requests/{request_id}/take/')
        configuration = Configuration.objects.get(pk=take_response.data['configuration'])
        self.assertEqual(configuration.mode, Configuration.Mode.ORDER)

        response = self.client.post(f'/api/configurations/{configuration.id}/request-prices/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['requested'], [self.base.name])

        price_request = PriceRequest.objects.get(pk=response.data['price_request'])
        line = price_request.lines.get()
        self.assertEqual(line.product, self.base)
        self.assertFalse(line.is_imported)

        answer_price_request_line(line, self.buyurtmachi, cost_price=Decimal('18000000'))
        configuration.refresh_from_db()
        self.assertFalse(configuration.needs_base_price)
        self.assertEqual(configuration.total_price, Decimal('18000000'))


class PriceRequestReturnTests(APITestCase):
    """29-§4(a): logist/deklarant izoh bilan buyurtmachiga qaytaradi."""

    def setUp(self):
        self.logist = User.objects.create_user('log', password='p', role=User.Role.LOGIST)
        self.declarant = User.objects.create_user('dek', password='p', role=User.Role.DECLARANT)
        self.buyurtmachi = User.objects.create_user('buy', password='p', role=User.Role.SUPPLIER)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        base = Product.objects.create(sku='HP-R1', name='HP R1', kind=Product.Kind.MACHINE)
        self.product = Product.objects.create(
            sku='CHIP-R1', name='ChipR1', kind=Product.Kind.COMPONENT, is_imported=True,
        )
        configuration = Configuration.objects.create(
            base_product=base, created_by=self.engineer, mode=Configuration.Mode.BUILD,
        )
        ConfigurationItem.objects.create(
            configuration=configuration, component=self.product, label='Chip', quantity=1,
        )
        self.price_request = open_price_request(
            configuration, self.engineer, lines=[(self.product, Decimal('1'))],
        )
        self.line = self.price_request.lines.get()

    def test_logist_returns_with_comment(self):
        line = return_price_request_line(self.line, self.logist, 'Yukni tashiy olmayman')
        self.assertEqual(line.status, PriceRequest.Status.WAITING_SUPPLIER)
        self.assertIsNone(line.logistics_filled_at)
        self.assertFalse(line.is_imported)
        note = Notification.objects.get(
            user=self.buyurtmachi, entity='PriceRequest', object_id=str(self.price_request.id),
        )
        self.assertIn('qaytarildi', note.title)
        self.assertIn('Logist', note.message)

    def test_return_without_comment_is_rejected(self):
        with self.assertRaises(ValidationError):
            return_price_request_line(self.line, self.logist, '')

    def test_declarant_returns_after_logistics_filled(self):
        fill_price_request_logistics(self.line, self.logist, logistics_total=Decimal('50000'))
        self.line.refresh_from_db()
        line = return_price_request_line(self.line, self.declarant, "Ma'lumot yetarli emas")
        self.assertIsNone(line.customs_filled_at)
        self.assertFalse(line.is_imported)
        note = Notification.objects.get(
            user=self.buyurtmachi, entity='PriceRequest', object_id=str(self.price_request.id),
        )
        self.assertIn('Deklarant', note.message)

    def test_supplier_cannot_return(self):
        with self.assertRaises(PermissionDenied):
            return_price_request_line(self.line, self.buyurtmachi, 'nega')

    def test_answered_line_cannot_be_returned(self):
        self.line.is_imported = False
        self.line.save()
        answer_price_request_line(self.line, self.buyurtmachi, cost_price=Decimal('1000'))
        self.line.refresh_from_db()
        with self.assertRaises(ValidationError):
            return_price_request_line(self.line, self.logist, 'kech qoldim')


class PriceRequestQuantityChangeTests(APITestCase):
    """29-§4(b): partiya o'zgarsa ochiq so'rov qatorlari ham ergashadi."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.logist = User.objects.create_user('log', password='p', role=User.Role.LOGIST)
        self.buyurtmachi = User.objects.create_user('buy', password='p', role=User.Role.SUPPLIER)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.base = Product.objects.create(sku='HP-Q1', name='HP Q1', kind=Product.Kind.MACHINE)
        self.imported_part = Product.objects.create(
            sku='CHIP-Q1', name='ChipQ1', kind=Product.Kind.COMPONENT, is_imported=True,
        )
        self.local_part = Product.objects.create(sku='LOCAL-Q1', name='LocalQ1', kind=Product.Kind.COMPONENT)

        self.client.force_authenticate(self.sales)
        request_id = self.client.post('/api/configuration-requests/', {
            'text': '10 ta HP Q1', 'base_product': self.base.id,
            'client': self.mijoz.id, 'quantity': 10,
        }, format='json').data['id']
        self.client.force_authenticate(self.engineer)
        take_response = self.client.post(
            f'/api/configuration-requests/{request_id}/take/', {'mode': 'build'}, format='json',
        )
        self.configuration = Configuration.objects.get(pk=take_response.data['configuration'])
        ConfigurationItem.objects.create(
            configuration=self.configuration, component=self.imported_part, label='Chip', quantity=1,
        )
        ConfigurationItem.objects.create(
            configuration=self.configuration, component=self.local_part, label='Local', quantity=1,
        )
        response = self.client.post(f'/api/configurations/{self.configuration.id}/request-prices/')
        self.price_request = PriceRequest.objects.get(pk=response.data['price_request'])
        self.import_line = self.price_request.lines.get(product=self.imported_part)
        self.local_line = self.price_request.lines.get(product=self.local_part)
        declarant = User.objects.create_user('dek2', password='p', role=User.Role.DECLARANT)
        fill_price_request_logistics(self.import_line, self.logist, logistics_total=Decimal('50000'))
        fill_price_request_customs(
            self.import_line, declarant, tnved_code='1234', duty_percent=Decimal('10'),
        )

    def test_quantity_change_resets_logistics_but_keeps_customs(self):
        self.client.force_authenticate(self.sales)
        response = self.client.post(
            f'/api/configurations/{self.configuration.id}/change-quantity/',
            {'quantity': 100}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)

        self.import_line.refresh_from_db()
        self.assertEqual(self.import_line.quantity, Decimal('100'))
        self.assertIsNone(self.import_line.logistics_filled_at)
        self.assertEqual(self.import_line.status, PriceRequest.Status.WAITING_LOGISTICS)
        # Bojxona qismi saqlanadi
        self.assertEqual(self.import_line.tnved_code, '1234')
        self.assertEqual(self.import_line.duty_percent, Decimal('10.00'))

        note = Notification.objects.filter(
            user=self.logist, entity='PriceRequest', title__contains='qayta kerak',
        )
        self.assertTrue(note.exists())

    def test_local_line_quantity_follows_without_state_change(self):
        self.client.force_authenticate(self.sales)
        response = self.client.post(
            f'/api/configurations/{self.configuration.id}/change-quantity/',
            {'quantity': 100}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.local_line.refresh_from_db()
        self.assertEqual(self.local_line.quantity, Decimal('100'))
        self.assertEqual(self.local_line.status, PriceRequest.Status.WAITING_SUPPLIER)


class PriceRequestCancelChainTests(APITestCase):
    """29-§4(c): zanjir bekor bo'lsa ochiq narx so'rovi ham bekor bo'ladi."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.logist = User.objects.create_user('log', password='p', role=User.Role.LOGIST)
        self.declarant = User.objects.create_user('dek', password='p', role=User.Role.DECLARANT)
        self.buyurtmachi = User.objects.create_user('buy', password='p', role=User.Role.SUPPLIER)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.base = Product.objects.create(sku='HP-C1', name='HP C1', kind=Product.Kind.MACHINE)
        self.part = Product.objects.create(sku='PART-C1', name='PartC1', kind=Product.Kind.COMPONENT)

        self.client.force_authenticate(self.sales)
        self.request_id = self.client.post('/api/configuration-requests/', {
            'text': '1 ta', 'base_product': self.base.id,
            'client': self.mijoz.id, 'quantity': 1,
        }, format='json').data['id']
        self.client.force_authenticate(self.engineer)
        take_response = self.client.post(
            f'/api/configuration-requests/{self.request_id}/take/', {'mode': 'build'}, format='json',
        )
        self.configuration = Configuration.objects.get(pk=take_response.data['configuration'])
        ConfigurationItem.objects.create(
            configuration=self.configuration, component=self.part, label='Part', quantity=1,
        )
        response = self.client.post(f'/api/configurations/{self.configuration.id}/request-prices/')
        self.price_request = PriceRequest.objects.get(pk=response.data['price_request'])

    def test_cancel_chain_cancels_open_price_request(self):
        from apps.configurator.services import cancel_chain

        request_obj = ConfigurationRequest.objects.get(pk=self.request_id)
        cancel_chain(request_obj, self.sales, 'Mijoz voz kechdi')

        self.price_request.refresh_from_db()
        self.assertEqual(self.price_request.status, PriceRequest.Status.CANCELLED)
        self.assertFalse(
            Notification.objects.filter(
                user=self.buyurtmachi, entity='PriceRequest',
                object_id=str(self.price_request.id), is_read=False,
            ).exists(),
        )

    def test_answered_request_untouched_by_cancel_chain(self):
        from apps.configurator.services import cancel_chain

        line = self.price_request.lines.get()
        answer_price_request_line(line, self.buyurtmachi, cost_price=Decimal('1000'))
        self.price_request.refresh_from_db()
        self.assertEqual(self.price_request.status, PriceRequest.Status.ANSWERED)

        request_obj = ConfigurationRequest.objects.get(pk=self.request_id)
        cancel_chain(request_obj, self.sales, 'Kech qolindi')
        self.price_request.refresh_from_db()
        self.assertEqual(self.price_request.status, PriceRequest.Status.ANSWERED)


class PriceRequestRoadmapAutoFillTests(APITestCase):
    """29-§5: kod eslab qolingani uchun avtomatik to'ldirilgan customs bosqichi
    "bajarilgan" emas, "o'tkazildi" bo'lib chizilsin; kim to'ldirgani ko'rinsin."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.logist = User.objects.create_user('log', password='p', role=User.Role.LOGIST)
        self.declarant = User.objects.create_user('dek', password='p', role=User.Role.DECLARANT)
        self.admin = User.objects.create_user('adm', password='p', role=User.Role.ADMIN)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.base = Product.objects.create(sku='HP-A1', name='HP A1', kind=Product.Kind.MACHINE)

    def _take_and_request(self, imported_part):
        self.client.force_authenticate(self.sales)
        request_id = self.client.post('/api/configuration-requests/', {
            'text': '1 ta', 'base_product': self.base.id,
            'client': self.mijoz.id, 'quantity': 1,
        }, format='json').data['id']
        self.client.force_authenticate(self.engineer)
        take_response = self.client.post(
            f'/api/configuration-requests/{request_id}/take/', {'mode': 'build'}, format='json',
        )
        configuration = Configuration.objects.get(pk=take_response.data['configuration'])
        ConfigurationItem.objects.create(
            configuration=configuration, component=imported_part, label='Chip', quantity=1,
        )
        self.client.post(f'/api/configurations/{configuration.id}/request-prices/')
        return request_id, configuration

    def test_auto_filled_customs_step_is_skipped_not_done(self):
        imported_part = Product.objects.create(
            sku='CHIP-A1', name='ChipA1', kind=Product.Kind.COMPONENT, is_imported=True,
            tnved_code='8471.30', duty_percent=Decimal('10'),
        )
        request_id, configuration = self._take_and_request(imported_part)
        line = PriceRequestLine.objects.get(product=imported_part)
        self.assertTrue(line.customs_auto_filled)
        fill_price_request_logistics(line, self.logist, logistics_total=Decimal('50000'))

        self.client.force_authenticate(self.admin)
        response = self.client.get(f'/api/configuration-requests/{request_id}/roadmap/')
        steps = {s['key']: s for s in response.data['steps']}
        self.assertEqual(steps['customs_clearance']['state'], 'skipped')

    def test_manually_filled_customs_step_is_done_with_actor(self):
        imported_part = Product.objects.create(
            sku='CHIP-A2', name='ChipA2', kind=Product.Kind.COMPONENT, is_imported=True,
        )
        request_id, configuration = self._take_and_request(imported_part)
        line = PriceRequestLine.objects.get(product=imported_part)
        fill_price_request_logistics(line, self.logist, logistics_total=Decimal('50000'))
        line.refresh_from_db()
        fill_price_request_customs(line, self.declarant, tnved_code='1', duty_percent=0)

        self.client.force_authenticate(self.admin)
        response = self.client.get(f'/api/configuration-requests/{request_id}/roadmap/')
        steps = {s['key']: s for s in response.data['steps']}
        self.assertEqual(steps['customs_clearance']['state'], 'done')
        self.assertEqual(steps['customs_clearance']['actor']['full_name'], self.declarant.display_name)
        self.assertEqual(steps['logistics_quote']['actor']['full_name'], self.logist.display_name)

    def test_send_to_customs_reopens_the_step(self):
        imported_part = Product.objects.create(
            sku='CHIP-A3', name='ChipA3', kind=Product.Kind.COMPONENT, is_imported=True,
            tnved_code='8471.30', duty_percent=Decimal('10'),
        )
        request_id, configuration = self._take_and_request(imported_part)
        line = PriceRequestLine.objects.get(product=imported_part)
        fill_price_request_logistics(line, self.logist, logistics_total=Decimal('50000'))
        line.refresh_from_db()

        buyurtmachi = User.objects.create_user('buy', password='p', role=User.Role.SUPPLIER)
        send_price_request_line_to_customs(line, buyurtmachi)

        self.client.force_authenticate(self.admin)
        response = self.client.get(f'/api/configuration-requests/{request_id}/roadmap/')
        steps = {s['key']: s for s in response.data['steps']}
        self.assertEqual(steps['customs_clearance']['state'], 'current')
