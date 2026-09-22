from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.inventory.models import Product
from apps.sales.models import Contract, ContractDocument, ContractItem


class ContractDocumentTests(APITestCase):
    """13-§1: shartnoma matni — bugalter yuklaydi va saytda tahrirlaydi."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.sales2 = User.objects.create_user('sal2', password='p', role=User.Role.SALES)
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.admin = User.objects.create_user('adm', password='p', role=User.Role.ADMIN)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.supplier = User.objects.create_user('buy', password='p', role=User.Role.SUPPLIER)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.product = Product.objects.create(
            sku='HP-880', name='HP 880', sale_price=Decimal('12000000'),
        )
        self.contract = Contract.objects.create(
            client=self.mijoz, total_amount=Decimal('13440000'),
            created_by=self.sales, status=Contract.Status.PENDING_BUGALTER,
        )
        ContractItem.objects.create(
            contract=self.contract, product=self.product, quantity=1,
            unit_price=Decimal('12000000'),
        )

    def test_get_lazily_creates_document(self):
        self.client.force_authenticate(self.bugalter)
        response = self.client.get(f'/api/contracts/{self.contract.id}/document/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['body'], '')
        self.assertTrue(response.data['can_edit'])
        self.assertTrue(ContractDocument.objects.filter(contract=self.contract).exists())

    def test_engineer_and_supplier_have_no_access(self):
        for user in (self.engineer, self.supplier):
            self.client.force_authenticate(user)
            response = self.client.get(f'/api/contracts/{self.contract.id}/document/')
            self.assertEqual(response.status_code, 403, (user.username, response.data))

    def test_sales_owner_can_read_not_edit(self):
        self.client.force_authenticate(self.sales)
        response = self.client.get(f'/api/contracts/{self.contract.id}/document/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data['can_edit'])

        response = self.client.put(
            f'/api/contracts/{self.contract.id}/document/',
            {'body': 'x'}, format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_other_sales_cannot_read(self):
        """Egasi bo'lmagan sales — get_queryset uni umuman ko'rmaydi (404)."""
        self.client.force_authenticate(self.sales2)
        response = self.client.get(f'/api/contracts/{self.contract.id}/document/')
        self.assertEqual(response.status_code, 404)

    def test_admin_can_read_not_edit(self):
        """13-§1: tahrir hozircha FAQAT bugalterda — admin ham yo'q."""
        self.client.force_authenticate(self.admin)
        response = self.client.get(f'/api/contracts/{self.contract.id}/document/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data['can_edit'])

        response = self.client.put(
            f'/api/contracts/{self.contract.id}/document/',
            {'body': 'x'}, format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_bugalter_saves_new_version_each_time(self):
        self.client.force_authenticate(self.bugalter)
        r1 = self.client.put(
            f'/api/contracts/{self.contract.id}/document/',
            {'body': '<p>Birinchi</p>'}, format='json',
        )
        self.assertEqual(r1.status_code, 200, r1.data)
        r2 = self.client.put(
            f'/api/contracts/{self.contract.id}/document/',
            {'body': '<p>Ikkinchi</p>'}, format='json',
        )
        self.assertEqual(r2.status_code, 200, r2.data)

        versions = self.client.get(
            f'/api/contracts/{self.contract.id}/document/versions/',
        )
        self.assertEqual(len(versions.data), 2)
        self.assertEqual(versions.data[0]['body'], '<p>Ikkinchi</p>')  # -created_at

    def test_edit_locked_after_didox_sent(self):
        Contract.objects.filter(pk=self.contract.pk).update(
            status=Contract.Status.PENDING_DIDOX,
        )
        self.client.force_authenticate(self.bugalter)
        response = self.client.put(
            f'/api/contracts/{self.contract.id}/document/',
            {'body': 'x'}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('Didoxga', str(response.data['detail']))

    def test_placeholders_resolve_for_everyone_with_document_access(self):
        """QOLGAN-ISHLAR #3: jami summa PRICE_FIELDS (qator narxi) qoidasiga
        kirmaydi — hujjatga kirgan har kim (bugalter ham) uni ko'radi."""
        self.client.force_authenticate(self.bugalter)
        self.client.put(
            f'/api/contracts/{self.contract.id}/document/',
            {'body': '{{ contract.number }} — jami {{ total }}'}, format='json',
        )
        response = self.client.get(f'/api/contracts/{self.contract.id}/document/')
        self.assertIn(self.contract.number, response.data['body'])
        self.assertIn('13440000', response.data['body'])

        self.client.force_authenticate(self.sales)
        response = self.client.get(f'/api/contracts/{self.contract.id}/document/')
        self.assertIn('13440000', response.data['body'])

    def test_body_raw_stays_unrendered_for_editing(self):
        """QOLGAN-ISHLAR #2: `body_raw` — o'rin egallovchilar TO'LMAGAN, muharrir shuni saqlaydi."""
        self.client.force_authenticate(self.bugalter)
        self.client.put(
            f'/api/contracts/{self.contract.id}/document/',
            {'body': '{{ contract.number }} — jami {{ total }}'}, format='json',
        )
        response = self.client.get(f'/api/contracts/{self.contract.id}/document/')
        self.assertEqual(response.data['body_raw'], '{{ contract.number }} — jami {{ total }}')
        self.assertIn(self.contract.number, response.data['body'])  # body — render qilingan

    def test_upload_rejects_non_docx(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_authenticate(self.bugalter)
        response = self.client.post(
            f'/api/contracts/{self.contract.id}/document/upload/',
            {'file': SimpleUploadedFile('shartnoma.pdf', b'%PDF-1.4', content_type='application/pdf')},
            format='multipart',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('file', response.data)

    def test_upload_docx_converts_to_html_and_keeps_source_file(self):
        """13-§1 bosqich 3: `.docx` -> mammoth -> body; asl fayl saqlanadi."""
        from unittest.mock import patch

        from django.core.files.uploadedfile import SimpleUploadedFile

        self.client.force_authenticate(self.bugalter)
        fake_docx = SimpleUploadedFile(
            'shartnoma.docx', b'PK\x03\x04fake',
            content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        )
        with patch('mammoth.convert_to_html') as mocked:
            mocked.return_value.value = '<p>Yuklangan matn</p>'
            response = self.client.post(
                f'/api/contracts/{self.contract.id}/document/upload/',
                {'file': fake_docx}, format='multipart',
            )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['body'], '<p>Yuklangan matn</p>')

        document = ContractDocument.objects.get(contract=self.contract)
        self.assertEqual(document.body, '<p>Yuklangan matn</p>')
        self.assertTrue(document.source_file.name)
        self.assertEqual(document.versions.count(), 1)
