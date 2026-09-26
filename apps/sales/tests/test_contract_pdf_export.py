from decimal import Decimal
from unittest import skipUnless
from unittest.mock import patch

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.inventory.models import Product
from apps.sales.models import Contract, ContractItem, ContractTemplate
from apps.sales.services import (
    _contract_document_placeholders,
    _inline_legacy_styles,
    render_contract_document,
    render_contract_pdf_html,
    requisites_block_html,
    specification_block_html,
)


def _weasyprint_available():
    """22-§1(b): haqiqiy chizish faqat native GTK/Pango bor joyda (CI/konteyner)
    sinaladi — bu Windows sandbox'da yo'q, shuning uchun shu yerda o'tkazib
    yuboriladi (qolgan testlar `render_contract_pdf`ni mock qiladi)."""
    try:
        import weasyprint  # noqa: F401
    except OSError:
        return False
    return True


class RenderContractDocumentTests(APITestCase):
    """21-§3.3(a): qiymat kalitlari — hammasi to'ladi, `{{ }}` qolmaydi."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.mijoz_legal = Client.objects.create(
            type=Client.Type.LEGAL, company_name='OOO Test', inn='123456789',
            jshshir='11112222333344', mfo='00014', bank_name='Bank',
            account_number='2020000000000000001', director_name='Aliyev A.',
            director_title='Direktor', phone='+998900000001',
        )
        self.product = Product.objects.create(
            sku='HP-880', name='HP 880', sale_price=Decimal('12000000'), unit='dona',
        )
        self.contract = Contract.objects.create(
            client=self.mijoz_legal, created_by=self.sales,
        )
        ContractItem.objects.create(
            contract=self.contract, product=self.product, quantity=2,
            unit_price=Decimal('12000000'),
        )
        from apps.core.models import CompanyProfile

        self.company = CompanyProfile.load()
        self.company.name = 'Ombor CRM MChJ'
        self.company.inn = '987654321'
        self.company.city = 'г. Ташкент'
        self.company.director_name = 'Xamidxodjiyev N.B.'
        self.company.director_title = 'Bosh direktor'
        self.company.save()

    def test_all_known_keys_replaced(self):
        from apps.sales.services import KNOWN_CONTRACT_PLACEHOLDER_KEYS

        body = ' '.join(f'{{{{ {key} }}}}' for key in KNOWN_CONTRACT_PLACEHOLDER_KEYS)
        rendered = render_contract_document(self.contract, body)
        self.assertNotIn('{{', rendered)

    def test_unknown_key_left_untouched(self):
        rendered = render_contract_document(self.contract, '{{ clientt.inn }}')
        self.assertIn('{{ clientt.inn }}', rendered)

    def test_company_and_client_values(self):
        rendered = render_contract_document(
            self.contract, '{{ company.name }} / {{ client.name }}',
        )
        self.assertIn('Ombor CRM MChJ', rendered)
        self.assertIn('OOO Test', rendered)

    def test_total_words_present(self):
        values = _contract_document_placeholders(self.contract)
        self.assertIn('сум', values['contract.total_words'])


class HtmlEscapingTests(APITestCase):
    """22-§2: ma'lumotdan kelgan qiymatlar (sales matni EMAS) ekranlanadi —
    aks holda `<`/`>`/`&` bo'lgan nom HTML teg deb o'qilib jimgina yo'qoladi."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.mijoz = Client.objects.create(
            type=Client.Type.LEGAL, company_name='OOO "Standart & Ko" <VIP>',
            inn='123456789', jshshir='11112222333344', mfo='00014',
            bank_name='Bank', account_number='2020000000000000001',
            director_name='Aliyev A.', director_title='Direktor',
            phone='+998900000001',
        )
        self.product = Product.objects.create(
            sku='KBL-1', name='Kabel <2m> & adapter', sale_price=Decimal('100000'), unit='dona',
        )
        self.contract = Contract.objects.create(client=self.mijoz, created_by=self.sales)
        ContractItem.objects.create(
            contract=self.contract, product=self.product, quantity=1,
            unit_price=Decimal('100000'),
        )

    def test_specification_escapes_product_name(self):
        html = specification_block_html(self.contract)
        self.assertIn('Kabel &lt;2m&gt; &amp; adapter', html)
        self.assertNotIn('Kabel <2m> & adapter', html)

    def test_requisites_escapes_client_name(self):
        html = requisites_block_html(self.contract)
        self.assertIn('&lt;VIP&gt;', html)
        self.assertNotIn('<VIP>', html)

    def test_placeholder_values_are_escaped(self):
        values = _contract_document_placeholders(self.contract)
        self.assertIn('&amp;', values['client.name'] + values['company.name'])

    def test_pdf_frame_html_escapes_preamble_and_title(self):
        html = render_contract_pdf_html(self.contract)
        self.assertIn('&lt;VIP&gt;', html)
        self.assertNotIn('<VIP>', html)
        # Text still present, just escaped — not silently dropped
        self.assertIn('Standart', html)

    def test_sales_body_is_not_escaped(self):
        """Sales yozgan matn — allaqachon HTML, ekranlanmasin."""
        from apps.sales.services import set_contract_document_body

        set_contract_document_body(self.contract, self.sales, '<p><strong>Muhim</strong></p>')
        html = render_contract_pdf_html(self.contract)
        self.assertIn('<strong>Muhim</strong>', html)


class ContractDateSourceTests(APITestCase):
    """22-§3: raqam va matndagi sana bitta manbadan — `created_at`, `signed_at`
    bo'lmasa (draft holatida sana har kun o'qishda o'zgarib turmasligi kerak)."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )

    def test_date_uses_created_at_not_today(self):
        """`signed_at` yo'q (draft) — sana raqam bilan bir xil manbadan:
        shartnoma OCHILGAN kun, o'qish kuni emas."""
        contract = Contract.objects.create(client=self.mijoz, created_by=self.sales)
        Contract.objects.filter(pk=contract.pk).update(
            created_at='2026-09-23 10:00:00+00:00',
        )
        contract.refresh_from_db()
        values = _contract_document_placeholders(contract)
        self.assertIn('23 сентября', values['contract.date'])

    def test_signed_at_still_takes_priority(self):
        from datetime import date

        contract = Contract.objects.create(
            client=self.mijoz, created_by=self.sales, signed_at=date(2026, 1, 5),
        )
        values = _contract_document_placeholders(contract)
        self.assertIn('5 января', values['contract.date'])


class SpecificationBlockTests(APITestCase):
    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.product = Product.objects.create(
            sku='HP-880', name='HP 880', sale_price=Decimal('12000000'), unit='dona',
        )
        self.contract = Contract.objects.create(client=self.mijoz, created_by=self.sales)
        ContractItem.objects.create(
            contract=self.contract, product=self.product, quantity=2,
            unit_price=Decimal('12000000'),
        )

    def test_rows_and_total_and_words(self):
        html = specification_block_html(self.contract, language='ru')
        self.assertIn('HP 880', html)
        self.assertIn('ИТОГО', html)
        self.assertIn('сум', html)

    def test_empty_when_no_items(self):
        empty_contract = Contract.objects.create(client=self.mijoz, created_by=self.sales)
        self.assertEqual(specification_block_html(empty_contract), '')

    def test_individual_client_requisites_no_inn(self):
        html = requisites_block_html(self.contract)
        self.assertIn('Паспорт', html)
        self.assertIn('AA1112223', html)
        self.assertNotIn('ИНН: 123', html)

    def test_legal_client_requisites_has_inn_and_bank(self):
        legal = Client.objects.create(
            type=Client.Type.LEGAL, company_name='OOO Test', inn='123456789',
            jshshir='55556666777788', mfo='00014', bank_name='Bank',
            account_number='2020000000000000001', director_name='Aliyev A.',
            phone='+998900000002',
        )
        legal_contract = Contract.objects.create(client=legal, created_by=self.sales)
        html = requisites_block_html(legal_contract)
        self.assertIn('ИНН: 123456789', html)
        self.assertIn('Bank', html)
        self.assertNotIn('Паспорт', html)


class InlineLegacyStylesTests(APITestCase):
    """21-§3.7: Quill sinflari saqlashda inline uslubga ham ko'chiriladi."""

    def test_align_center_gets_inline_style(self):
        html = _inline_legacy_styles('<p class="ql-align-center">Salom</p>')
        self.assertIn('class="ql-align-center"', html)
        self.assertIn('text-align: center', html)

    def test_indent_level_gets_margin(self):
        html = _inline_legacy_styles('<p class="ql-indent-2">Salom</p>')
        self.assertIn('margin-left: 6em', html)

    def test_existing_style_merged_not_overwritten(self):
        html = _inline_legacy_styles(
            '<p class="ql-align-right" style="color: red">Salom</p>',
        )
        self.assertIn('color: red', html)
        self.assertIn('text-align: right', html)

    def test_plain_tag_without_ql_class_untouched(self):
        html = _inline_legacy_styles('<p class="other">Salom</p>')
        self.assertEqual(html, '<p class="other">Salom</p>')


class ContractDocumentPatchInlineStyleTests(APITestCase):
    """PATCH /document/ orqali saqlangan matn — sinf ham, inline uslub ham bor."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.contract = Contract.objects.create(client=self.mijoz, created_by=self.sales)
        ContractItem.objects.create(
            contract=self.contract,
            product=Product.objects.create(sku='HP-880', name='HP 880'),
            quantity=1, unit_price=Decimal('1000000'),
        )

    def test_saved_body_has_inline_style_alongside_class(self):
        self.client.force_authenticate(self.sales)
        response = self.client.patch(
            f'/api/contracts/{self.contract.id}/document/',
            {'body': '<p class="ql-align-center">Markazda</p>'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn('ql-align-center', response.data['body_raw'])
        self.assertIn('text-align: center', response.data['body_raw'])


class RenderContractPdfHtmlTests(APITestCase):
    """`render_contract_pdf_html` — WeasyPrint'ga uzatiladigan ramka HTML'i.

    Bu haqiqiy chizish (`weasyprint.HTML(...).write_pdf()`) emas — shu
    sabab Windows sandbox'da native GTK/Pango kutubxonasisiz ham ishlaydi;
    productionda (Linux) xuddi shu HTML WeasyPrint orqali A4 PDF'ga o'tadi.
    """

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.contract = Contract.objects.create(client=self.mijoz, created_by=self.sales)
        ContractItem.objects.create(
            contract=self.contract,
            product=Product.objects.create(sku='HP-880', name='HP 880', unit='dona'),
            quantity=1, unit_price=Decimal('1000000'),
        )

    def test_contains_number_terms_and_specification(self):
        template = ContractTemplate.objects.create(
            name='Standart', body='<p>Shart: {{ contract.number }}</p>', created_by=self.sales,
        )
        from apps.sales.services import attach_contract_template

        attach_contract_template(self.contract, template, self.sales)
        html = render_contract_pdf_html(self.contract)
        self.assertIn(self.contract.number, html)
        self.assertIn('specification', html)
        self.assertIn('requisites', html)
        self.assertNotIn('{{', html)

    def test_align_center_class_still_present_for_frame_css_fallback(self):
        """21-§3.7: ramka CSS'i ql-align-* sinflarini qayta e'lon qiladi —
        inline uslub yetarli bo'lmagan eski yozuvlar uchun ikkinchi himoya."""
        from apps.sales.services import set_contract_document_body

        set_contract_document_body(
            self.contract, self.sales, '<p class="ql-align-center">Markazda</p>',
        )
        html = render_contract_pdf_html(self.contract)
        self.assertIn('ql-align-center', html)
        self.assertIn('text-align: center', html)

    @skipUnless(_weasyprint_available(), 'WeasyPrint kutubxonalari yo\'q (native GTK/Pango)')
    def test_real_pdf_bytes(self):
        """22-§1(b): mock emas — haqiqiy WeasyPrint chaqiriladi, natija
        chinakam PDF baytlari bo'lishi kerak. Bu depo Windows sandbox'da
        o'tkazib yuboriladi, konteyner/CI'da (apt paketlari bilan) yuradi."""
        from apps.sales.services import render_contract_pdf

        pdf = render_contract_pdf(self.contract)
        self.assertTrue(pdf.startswith(b'%PDF'))


class ContractPdfExportViewTests(APITestCase):
    """21-§3.7: `GET /document/export/?format=pdf` — view darajasidagi huquq/javob.

    `render_contract_pdf` (WeasyPrint chaqiruvchi funksiya) mock qilinadi —
    haqiqiy `weasyprint` paketi bu Windows sandbox'da GTK/Pango yo'qligi
    sababli import bo'lmaydi (native dependency); shu bois HTML yig'ish
    (`render_contract_pdf_html`, yuqoridagi klass) alohida, haqiqiy kod
    bilan sinaladi, faqat oxirgi native chizish bosqichi mock qilinadi.
    """

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.sales2 = User.objects.create_user('sal2', password='p', role=User.Role.SALES)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.contract = Contract.objects.create(client=self.mijoz, created_by=self.sales)
        ContractItem.objects.create(
            contract=self.contract,
            product=Product.objects.create(sku='HP-880', name='HP 880'),
            quantity=1, unit_price=Decimal('1000000'),
        )

    @patch('apps.sales.services.render_contract_pdf')
    def test_export_returns_pdf_content_type(self, mock_render):
        mock_render.return_value = b'%PDF-1.4 fake'
        self.client.force_authenticate(self.sales)
        response = self.client.get(f'/api/contracts/{self.contract.id}/document/export/')
        self.assertEqual(response.status_code, 200, getattr(response, 'data', response.content))
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertEqual(response.content, b'%PDF-1.4 fake')

    def test_export_forbidden_for_non_owner_sales(self):
        self.client.force_authenticate(self.sales2)
        response = self.client.get(f'/api/contracts/{self.contract.id}/document/export/')
        self.assertEqual(response.status_code, 404)

    def test_export_forbidden_for_engineer(self):
        """Engineer ContractViewSet.get_queryset()da umuman yo'q — 404."""
        self.client.force_authenticate(self.engineer)
        response = self.client.get(f'/api/contracts/{self.contract.id}/document/export/')
        self.assertEqual(response.status_code, 404)

    @patch('apps.sales.services.render_contract_pdf')
    def test_unsupported_format_rejected(self, mock_render):
        """`?format=pdf` dan boshqasi — DRF'ning o'z format-negotiation'i 404 beradi
        (`PDFRenderer` yagona ro'yxatdagi renderer — view kodi ishga tushmaydi)."""
        self.client.force_authenticate(self.sales)
        response = self.client.get(
            f'/api/contracts/{self.contract.id}/document/export/?format=docx',
        )
        self.assertEqual(response.status_code, 404)
        mock_render.assert_not_called()


class PrepaymentDaysFieldTests(APITestCase):
    """22-§5: `prepayment_days` — huquqiy to'lov sharti, bron muddati EMAS."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )

    def test_defaults_from_company_reservation_days_but_is_own_field(self):
        from apps.core.models import CompanyProfile

        company = CompanyProfile.load()
        company.contract_reservation_days = 3
        company.save()
        contract = Contract.objects.create(client=self.mijoz, created_by=self.sales)
        self.assertEqual(contract.prepayment_days, 3)

        # Bron muddati keyin o'zgarsa ham — HUQUQIY hujjatdagi raqam qotib qoladi
        company.contract_reservation_days = 30
        company.save()
        contract.refresh_from_db()
        self.assertEqual(contract.prepayment_days, 3)

    def test_explicit_value_not_overridden(self):
        contract = Contract.objects.create(
            client=self.mijoz, created_by=self.sales, prepayment_days=14,
        )
        self.assertEqual(contract.prepayment_days, 14)

    def test_placeholder_uses_contract_field(self):
        contract = Contract.objects.create(
            client=self.mijoz, created_by=self.sales, prepayment_days=7,
        )
        values = _contract_document_placeholders(contract)
        self.assertEqual(values['contract.prepayment_days'], '7')

    def test_exposed_in_serializer(self):
        product = Product.objects.create(sku='HP-880', name='HP 880')
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/contracts/', {
            'client': self.mijoz.id, 'prepayment_days': 10,
            'items': [{'product': product.id, 'quantity': 1, 'unit_price': '1000000'}],
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data['prepayment_days'], 10)
