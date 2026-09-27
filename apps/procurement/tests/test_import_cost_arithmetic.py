from decimal import Decimal

from django.test import TestCase

from apps.inventory.models import Product
from apps.procurement.models import ImportCostSheet


class ImportCostArithmeticTests(TestCase):
    """24-§9.1: eng muhim testlar — har birida QO'LDA hisoblangan aniq son.

    BQ = tovar qiymati + chegaragacha yetkazish
    Boj = BQ x duty_percent / 100 (yoki qo'lda kiritilgan duty_amount)
    QQS = (BQ + boj + aksiz) x 12% — INVOYSDAN EMAS
    Bojxona yig'imi = qat'iy summa
    Jami tannarx = tovar + TO'LIQ logistika + bojxona xarajatlari
    Dona tannarx = jami tannarx / miqdor
    """

    def setUp(self):
        self.product = Product.objects.create(sku='IMP-1', name='Import mahsulot')

    def _sheet(self, **kwargs):
        defaults = dict(
            product=self.product, quantity=Decimal('10'),
            currency='USD', goods_price=Decimal('1000'),
            exchange_rate=Decimal('12500'),
        )
        defaults.update(kwargs)
        return ImportCostSheet.objects.create(**defaults)

    def test_customs_value_is_goods_plus_freight_to_border(self):
        # goods_uzs = 1000 * 12500 = 12 500 000
        sheet = self._sheet(freight_to_border=Decimal('500000'))
        self.assertEqual(sheet.goods_uzs, Decimal('12500000.0000'))
        self.assertEqual(sheet.customs_value, Decimal('13000000.0000'))

    def test_duty_from_percent(self):
        # BQ = 12 500 000 + 0 = 12 500 000; boj = 12 500 000 * 10% = 1 250 000
        sheet = self._sheet(duty_percent=Decimal('10'))
        self.assertEqual(sheet.duty, Decimal('1250000.00000'))

    def test_duty_amount_overrides_percent(self):
        sheet = self._sheet(duty_percent=Decimal('10'), duty_amount=Decimal('999999'))
        self.assertEqual(sheet.duty, Decimal('999999'))

    def test_vat_base_is_customs_value_plus_duty_not_invoice(self):
        """§2.1 4-qadam: eng ko'p xato qiladigan joy — QQS invoysdan emas."""
        # BQ = 12 500 000, boj (10%) = 1 250 000, aksiz = 0
        # QQS bazasi = 13 750 000, QQS (12%) = 1 650 000
        sheet = self._sheet(duty_percent=Decimal('10'), vat_percent=Decimal('12'))
        self.assertEqual(sheet.vat, Decimal('1650000.000000'))
        # Invoysdan (12 500 000) hisoblangan noto'g'ri qiymat bilan solishtiramiz
        wrong_vat_from_invoice = sheet.goods_uzs * Decimal('12') / 100
        self.assertNotEqual(sheet.vat, wrong_vat_from_invoice)

    def test_duty_zero_vat_still_calculated_from_customs_value(self):
        """Boj yo'q bo'lsa ham QQS BQ'dan hisoblanadi (§7 case 2)."""
        sheet = self._sheet(duty_percent=Decimal('0'), vat_percent=Decimal('12'))
        self.assertEqual(sheet.duty, 0)
        self.assertEqual(sheet.vat, sheet.customs_value * Decimal('12') / 100)
        self.assertGreater(sheet.vat, 0)

    def test_excise_included_in_vat_base(self):
        sheet = self._sheet(
            duty_percent=Decimal('10'), excise_amount=Decimal('200000'),
            vat_percent=Decimal('12'),
        )
        # BQ=12 500 000, boj=1 250 000, aksiz=200 000 -> baza=13 950 000
        expected_vat = Decimal('13950000.00000') * Decimal('12') / 100
        self.assertEqual(sheet.vat, expected_vat)

    def test_landed_total_includes_full_logistics(self):
        """`landed_total` — tovar + TO'LIQ logistika + bojxona xarajatlari."""
        sheet = self._sheet(
            logistics_total=Decimal('1000000'),
            freight_to_border=Decimal('500000'),
            duty_percent=Decimal('10'),
            customs_fee=Decimal('440000'),
            certificate_cost=Decimal('100000'),
            laboratory_cost=Decimal('50000'),
            declarant_fee=Decimal('300000'),
        )
        # goods_uzs=12 500 000, BQ=13 000 000, boj=1 300 000
        # qqs baza=14 300 000, qqs(12%)=1 716 000
        # customs_total = 1 300 000 + 1 716 000 + 440 000 + 100 000 + 50 000 + 300 000
        #               = 3 906 000
        # landed_total = 12 500 000 + 1 000 000 (TO'LIQ logistika) + 3 906 000
        #              = 17 406 000
        self.assertEqual(sheet.landed_total, Decimal('17406000.000000'))

    def test_unit_cost_divides_by_quantity_and_rounds(self):
        sheet = self._sheet(quantity=Decimal('3'), logistics_total=Decimal('1000000'))
        # goods_uzs=12 500 000, BQ=12 500 000 (freight_to_border=0), boj=0
        # qqs=12 500 000*12%=1 500 000, customs_total=1 500 000
        # landed=12 500 000+1 000 000+1 500 000=15 000 000
        # unit=15 000 000/3=5 000 000.00
        self.assertEqual(sheet.unit_cost, Decimal('5000000.00'))

    def test_unit_cost_zero_quantity_no_division_error(self):
        sheet = self._sheet(quantity=Decimal('0'))
        self.assertEqual(sheet.unit_cost, Decimal('0'))

    def test_exchange_rate_change_does_not_affect_saved_sheet(self):
        """Kurs varaqada QOTIB turadi — keyingi bugungi kurs bilan hisoblanmaydi."""
        sheet = self._sheet(exchange_rate=Decimal('12500'))
        goods_uzs_before = sheet.goods_uzs
        # "bugungi kurs" boshqacha bo'lsa ham eski varaqa o'z kursida qoladi
        sheet.refresh_from_db()
        self.assertEqual(sheet.goods_uzs, goods_uzs_before)
        self.assertEqual(sheet.exchange_rate, Decimal('12500.0000'))

    def test_freight_less_than_full_logistics_reduces_customs_base_only(self):
        """Chegaragacha < to'liq logistika — boj/QQS kichik, tannarx o'sha."""
        full_logistics = Decimal('2000000')
        partial_freight = Decimal('500000')
        sheet_partial = self._sheet(
            logistics_total=full_logistics, freight_to_border=partial_freight,
            duty_percent=Decimal('10'),
        )
        sheet_full = self._sheet(
            logistics_total=full_logistics, freight_to_border=full_logistics,
            duty_percent=Decimal('10'),
        )
        self.assertLess(sheet_partial.customs_value, sheet_full.customs_value)
        self.assertLess(sheet_partial.duty, sheet_full.duty)
        # Ikkalasida ham TO'LIQ logistika tannarxga kiradi
        self.assertEqual(
            sheet_partial.landed_total - sheet_partial.customs_total,
            sheet_full.landed_total - sheet_full.customs_total,
        )

    def test_vat_recoverable_false_includes_vat_in_landed_total(self):
        sheet = self._sheet(duty_percent=Decimal('10'), vat_recoverable=False)
        self.assertTrue(sheet.vat_in_cost)
        without_vat = sheet.customs_total - sheet.vat
        self.assertGreater(sheet.customs_total, without_vat)

    def test_vat_recoverable_true_excludes_vat_from_landed_total(self):
        """`vat` hisoblanadi (ko'rinadi), lekin `landed_total`ga kirmaydi —
        farq aynan `vat`ga teng (§9.1)."""
        common = dict(duty_percent=Decimal('10'), logistics_total=Decimal('1000000'))
        recoverable = self._sheet(vat_recoverable=True, **common)
        not_recoverable = self._sheet(vat_recoverable=False, **common)
        self.assertFalse(recoverable.vat_in_cost)
        self.assertGreater(recoverable.vat, 0)
        self.assertEqual(recoverable.vat, not_recoverable.vat)
        self.assertEqual(
            not_recoverable.landed_total - recoverable.landed_total,
            recoverable.vat,
        )

    def test_setting_changed_after_close_does_not_affect_closed_sheet(self):
        """§7 case 22: sozlama o'zgardi, varaqa yopilgan — hisob o'zgarmaydi
        (bayroq varaqaga NUSXALANGAN, CompanyProfile'dan har safar o'qilmaydi)."""
        from apps.core.models import CompanyProfile

        CompanyProfile.load()
        sheet = self._sheet(vat_recoverable=False, duty_percent=Decimal('10'))
        landed_before = sheet.landed_total

        profile = CompanyProfile.load()
        profile.vat_recoverable = True
        profile.save()

        sheet.refresh_from_db()
        self.assertFalse(sheet.vat_recoverable)
        self.assertEqual(sheet.landed_total, landed_before)
