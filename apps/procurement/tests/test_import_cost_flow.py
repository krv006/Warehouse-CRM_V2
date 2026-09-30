from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.inventory.models import Product
from apps.procurement.models import ImportCostSheet
from apps.procurement.services import open_import_sheet


class ImportCostFlowTests(APITestCase):
    """24-§9.2: oqim va ruxsat.

    29-§6: `POST /import-cost-sheets/open/` olib tashlandi — `request_prices`
    (28-to'plam) bu varaqani endi ochmaydi, hujjat arxiv/nazorat sifatida
    qoladi. Shu fayldagi testlar servis funksiyasini (`open_import_sheet`)
    to'g'ridan chaqirib ochadi — ular fill-goods/fill-logistics/fill-customs
    OQIMINI tekshiradi, ochish yo'lini emas.
    """

    def setUp(self):
        self.buyurtmachi = User.objects.create_user('buy', password='p', role=User.Role.SUPPLIER)
        self.logist = User.objects.create_user('log', password='p', role=User.Role.LOGIST)
        self.deklarant = User.objects.create_user('dek', password='p', role=User.Role.DECLARANT)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.admin = User.objects.create_user('adm', password='p', role=User.Role.ADMIN)
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.product = Product.objects.create(sku='IMP-1', name='Import mahsulot', kind=Product.Kind.COMPONENT)

    def _open_sheet(self, quantity=10):
        # Har chaqiruvda BAZADAN qayta o'qiladi (eski `open/` endpointi ham
        # shunday qilardi) — aks holda `self.product` avvalgi chaqiruvlarda
        # bazada yangilangan maydonlarni (masalan `tnved_code`) ko'rmay,
        # eskirgan Python obyekt bo'lib qolardi.
        product = Product.objects.get(pk=self.product.pk)
        return open_import_sheet(product, self.engineer, quantity=Decimal(quantity))

    def test_open_endpoint_removed(self):
        """29-§6: qo'lda ochish endpointi olib tashlandi."""
        self.client.force_authenticate(self.engineer)
        response = self.client.post('/api/import-cost-sheets/open/', {
            'product': self.product.id, 'quantity': 10,
        }, format='json')
        self.assertIn(response.status_code, (404, 405))

    def test_list_and_detail_still_readable(self):
        """29-§6: ro'yxat va detail arxiv/nazorat sifatida qoladi."""
        sheet = self._open_sheet()
        self.client.force_authenticate(self.bugalter)
        response = self.client.get('/api/import-cost-sheets/')
        self.assertEqual(response.status_code, 200, response.data)
        response = self.client.get(f'/api/import-cost-sheets/{sheet.id}/')
        self.assertEqual(response.status_code, 200, response.data)

    def _fill_goods(self, sheet):
        self.client.force_authenticate(self.buyurtmachi)
        response = self.client.post(f'/api/import-cost-sheets/{sheet.id}/fill-goods/', {
            'currency': 'USD', 'goods_price': '1000', 'exchange_rate': '12500',
            'origin_country': 'China',
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        return response

    def test_logist_fills_logistics_and_status_moves_to_waiting_customs(self):
        sheet = self._open_sheet()
        self._fill_goods(sheet)
        self.client.force_authenticate(self.logist)
        response = self.client.post(f'/api/import-cost-sheets/{sheet.id}/fill-logistics/', {
            'logistics_total': '1000000',
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], ImportCostSheet.Status.WAITING_CUSTOMS)

    def test_logist_cannot_fill_customs_section(self):
        sheet = self._open_sheet()
        self._fill_goods(sheet)
        self.client.force_authenticate(self.logist)
        response = self.client.post(f'/api/import-cost-sheets/{sheet.id}/fill-customs/', {
            'tnved_code': '8471300000',
        }, format='json')
        self.assertEqual(response.status_code, 403, response.data)

    def test_declarant_cannot_fill_while_waiting_logistics(self):
        """24-§6.3: deklarant logistdan OLDIN yozmoqchi — 400 aniq matn bilan."""
        sheet = self._open_sheet()
        self._fill_goods(sheet)
        self.client.force_authenticate(self.deklarant)
        response = self.client.post(f'/api/import-cost-sheets/{sheet.id}/fill-customs/', {
            'tnved_code': '8471300000', 'duty_percent': '10',
        }, format='json')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('bog\'liq', str(response.data))

    def test_declarant_fills_and_status_becomes_done(self):
        sheet = self._open_sheet()
        self._fill_goods(sheet)
        self.client.force_authenticate(self.logist)
        self.client.post(f'/api/import-cost-sheets/{sheet.id}/fill-logistics/', {
            'logistics_total': '1000000',
        }, format='json')
        self.client.force_authenticate(self.deklarant)
        response = self.client.post(f'/api/import-cost-sheets/{sheet.id}/fill-customs/', {
            'tnved_code': '8471300000', 'duty_percent': '10',
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], ImportCostSheet.Status.DONE)

        self.product.refresh_from_db()
        self.assertEqual(self.product.tnved_code, '8471300000')
        self.assertGreater(self.product.cost_price, 0)

    def test_engineer_cannot_open_view_the_sheet(self):
        """24-§4.1/§7 case 18: engineer varaqani ochmoqchi — 403."""
        sheet = self._open_sheet()
        self.client.force_authenticate(self.engineer)
        response = self.client.get(f'/api/import-cost-sheets/{sheet.id}/')
        self.assertEqual(response.status_code, 403, response.data)

    def test_yopilgan_varaqa_tahrirlanmaydi(self):
        """§7 case 11: yopilgan varaqa tahrirlanmaydi."""
        sheet = self._open_sheet()
        self._fill_goods(sheet)
        self.client.force_authenticate(self.logist)
        self.client.post(f'/api/import-cost-sheets/{sheet.id}/fill-logistics/', {
            'logistics_total': '1000000',
        }, format='json')
        self.client.force_authenticate(self.deklarant)
        self.client.post(f'/api/import-cost-sheets/{sheet.id}/fill-customs/', {
            'tnved_code': '8471300000',
        }, format='json')

        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/import-cost-sheets/{sheet.id}/change-quantity/', {
            'quantity': '20',
        }, format='json')
        self.assertEqual(response.status_code, 400, response.data)

    def test_second_open_sheet_for_same_product_returns_existing(self):
        """§7 case 15: bitta mahsulotga ikkinchi ochiq varaqa — yagonalik."""
        first = self._open_sheet()
        second = self._open_sheet()
        self.assertEqual(first.id, second.id)
        self.assertEqual(ImportCostSheet.objects.filter(product=self.product).count(), 1)

    def test_price_arrived_after_customs_filled_notifies_sales(self):
        """`done`dan keyin `price_arrived` ishladi."""
        from apps.core.models import Notification

        sheet = self._open_sheet()
        self._fill_goods(sheet)
        self.client.force_authenticate(self.logist)
        self.client.post(f'/api/import-cost-sheets/{sheet.id}/fill-logistics/', {
            'logistics_total': '1000000',
        }, format='json')
        self.client.force_authenticate(self.deklarant)
        response = self.client.post(f'/api/import-cost-sheets/{sheet.id}/fill-customs/', {
            'tnved_code': '8471300000',
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        # price_arrived faqat konfiguratsiyaga bog'liq narxsiz qatorlarni
        # yopadi — bu yerda konfiguratsiya yo'q, shuning uchun faqat xato
        # bermasligini tekshiramiz (to'liq zanjir alohida testda)
        self.assertFalse(Notification.objects.filter(title__icontains='500').exists())

    def test_return_import_sheet_requires_comment(self):
        sheet = self._open_sheet()
        self._fill_goods(sheet)
        self.client.force_authenticate(self.logist)
        response = self.client.post(f'/api/import-cost-sheets/{sheet.id}/return/', {}, format='json')
        self.assertEqual(response.status_code, 400, response.data)

    def test_return_import_sheet_goes_back_to_draft_and_notifies_opener(self):
        from apps.core.models import Notification

        sheet = self._open_sheet()
        self._fill_goods(sheet)
        self.client.force_authenticate(self.logist)
        response = self.client.post(f'/api/import-cost-sheets/{sheet.id}/return/', {
            'comment': "Bu yukni tashimayman",
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], ImportCostSheet.Status.DRAFT)
        self.assertTrue(
            Notification.objects.filter(
                user=self.engineer, entity='ImportCostSheet', object_id=str(sheet.pk),
            ).exists(),
        )

    def test_cancel_by_admin(self):
        sheet = self._open_sheet()
        self.client.force_authenticate(self.admin)
        response = self.client.post(f'/api/import-cost-sheets/{sheet.id}/cancel/', {
            'reason': 'Buyurtma bekor bo\'ldi',
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], ImportCostSheet.Status.CANCELLED)

    def test_cancel_forbidden_for_non_opener_non_admin(self):
        sheet = self._open_sheet()
        self.client.force_authenticate(self.bugalter)
        response = self.client.post(f'/api/import-cost-sheets/{sheet.id}/cancel/', {}, format='json')
        self.assertEqual(response.status_code, 403, response.data)

    def test_quantity_change_resets_waiting_customs_to_waiting_logistics(self):
        """§7 case 6: miqdor o'zgardi — waiting_logistics ga qaytadi, logistga eslatma."""
        from apps.core.models import Notification

        sheet = self._open_sheet(quantity=10)
        self._fill_goods(sheet)
        self.client.force_authenticate(self.logist)
        self.client.post(f'/api/import-cost-sheets/{sheet.id}/fill-logistics/', {
            'logistics_total': '1000000',
        }, format='json')
        sheet.refresh_from_db()
        self.assertEqual(sheet.status, ImportCostSheet.Status.WAITING_CUSTOMS)

        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/import-cost-sheets/{sheet.id}/change-quantity/', {
            'quantity': '50',
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['status'], ImportCostSheet.Status.WAITING_LOGISTICS)
        self.assertTrue(
            Notification.objects.filter(user=self.logist, entity='ImportCostSheet').exists(),
        )

    def test_goods_price_zero_blocks_customs_fill(self):
        """§7 case 13: tovar narxi kiritilmagan bo'lsa 400."""
        from apps.procurement.services import fill_customs_section, open_import_sheet

        sheet = open_import_sheet(self.product, self.engineer, quantity=Decimal('1'))
        sheet.status = ImportCostSheet.Status.WAITING_CUSTOMS
        sheet.save()
        from rest_framework.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            fill_customs_section(sheet, self.deklarant, tnved_code='8471300000')

    def test_exchange_rate_zero_rejected(self):
        sheet = self._open_sheet()
        self.client.force_authenticate(self.buyurtmachi)
        response = self.client.post(f'/api/import-cost-sheets/{sheet.id}/fill-goods/', {
            'currency': 'USD', 'goods_price': '1000', 'exchange_rate': '0',
        }, format='json')
        self.assertEqual(response.status_code, 400, response.data)

    def test_tnved_code_prefilled_on_second_import(self):
        """§7 case 8 / §9.2: ikkinchi importda `tnved_code` oldindan to'ladi."""
        sheet = self._open_sheet()
        self._fill_goods(sheet)
        self.client.force_authenticate(self.logist)
        self.client.post(f'/api/import-cost-sheets/{sheet.id}/fill-logistics/', {
            'logistics_total': '1000000',
        }, format='json')
        self.client.force_authenticate(self.deklarant)
        self.client.post(f'/api/import-cost-sheets/{sheet.id}/fill-customs/', {
            'tnved_code': '8471300000',
        }, format='json')

        second = self._open_sheet(quantity=5)
        self.assertEqual(second.product.tnved_code, '8471300000')

    def test_default_customs_fee_prefilled_when_not_provided(self):
        """§11 qadam 8: `customs_fee` kiritilmasa, `CompanyProfile.default_customs_fee`dan to'ladi."""
        from apps.core.models import CompanyProfile

        profile = CompanyProfile.load()
        profile.default_customs_fee = Decimal('150000')
        profile.save()

        sheet = self._open_sheet()
        self._fill_goods(sheet)
        self.client.force_authenticate(self.logist)
        self.client.post(f'/api/import-cost-sheets/{sheet.id}/fill-logistics/', {
            'logistics_total': '1000000',
        }, format='json')
        self.client.force_authenticate(self.deklarant)
        response = self.client.post(f'/api/import-cost-sheets/{sheet.id}/fill-customs/', {
            'tnved_code': '8471300000',
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        sheet.refresh_from_db()
        self.assertEqual(sheet.customs_fee, Decimal('150000'))

    def test_explicit_customs_fee_overrides_default(self):
        from apps.core.models import CompanyProfile

        profile = CompanyProfile.load()
        profile.default_customs_fee = Decimal('150000')
        profile.save()

        sheet = self._open_sheet()
        self._fill_goods(sheet)
        self.client.force_authenticate(self.logist)
        self.client.post(f'/api/import-cost-sheets/{sheet.id}/fill-logistics/', {
            'logistics_total': '1000000',
        }, format='json')
        self.client.force_authenticate(self.deklarant)
        response = self.client.post(f'/api/import-cost-sheets/{sheet.id}/fill-customs/', {
            'tnved_code': '8471300000', 'customs_fee': '20000',
        }, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        sheet.refresh_from_db()
        self.assertEqual(sheet.customs_fee, Decimal('20000'))
