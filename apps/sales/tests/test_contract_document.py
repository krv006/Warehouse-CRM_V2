from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.inventory.models import Product
from apps.sales.models import Contract, ContractDocument, ContractItem, ContractTemplate


class ContractDocumentTests(APITestCase):
    """21-§3.2/3.6: shartnoma matni — shablon + avtomatik bloklar, HTML
    to'g'ridan-to'g'ri tahrirlanadi (`.docx`/Collabora/WOPI olib tashlandi)."""

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
        self.template = ContractTemplate.objects.create(
            name='Standart', body='<p>Shartnoma {{ contract.number }}</p>',
            created_by=self.sales,
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

    def test_sales_owner_can_read_and_edit(self):
        """21-§3.6: sales (egasi) endi yangi — ilgari faqat bugalter edi."""
        self.client.force_authenticate(self.sales)
        response = self.client.get(f'/api/contracts/{self.contract.id}/document/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['can_edit'])

    def test_other_sales_cannot_read(self):
        """Egasi bo'lmagan sales — get_queryset uni umuman ko'rmaydi (404)."""
        self.client.force_authenticate(self.sales2)
        response = self.client.get(f'/api/contracts/{self.contract.id}/document/')
        self.assertEqual(response.status_code, 404)

    def test_other_sales_cannot_edit(self):
        self.client.force_authenticate(self.sales2)
        response = self.client.patch(
            f'/api/contracts/{self.contract.id}/document/', {'body': '<p>x</p>'}, format='json',
        )
        self.assertEqual(response.status_code, 404)

    def test_admin_can_read_and_edit(self):
        self.client.force_authenticate(self.admin)
        response = self.client.get(f'/api/contracts/{self.contract.id}/document/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['can_edit'])

    def test_edit_locked_after_didox_sent(self):
        """Holat chegarasi o'zgarmaydi — Didoxga ketgach hech kim tahrirlamaydi."""
        Contract.objects.filter(pk=self.contract.pk).update(
            status=Contract.Status.PENDING_DIDOX,
        )
        self.client.force_authenticate(self.admin)
        response = self.client.get(f'/api/contracts/{self.contract.id}/document/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data['can_edit'])

        response = self.client.patch(
            f'/api/contracts/{self.contract.id}/document/', {'body': '<p>x</p>'}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('Didoxga', str(response.data['detail']))

    def test_edit_forbidden_for_engineer_supplier(self):
        """Engineer/buyurtmachi ContractViewSet.get_queryset()da umuman yo'q — 404."""
        for user in (self.engineer, self.supplier):
            self.client.force_authenticate(user)
            response = self.client.patch(
                f'/api/contracts/{self.contract.id}/document/', {'body': '<p>x</p>'}, format='json',
            )
            self.assertEqual(response.status_code, 404, (user.username, response.data))

    def test_sales_edits_document_text(self):
        """21-§3.6: sales o'z shartnomasi matnini tahrirlaydi — 200 (yangi)."""
        self.client.force_authenticate(self.sales)
        response = self.client.patch(
            f'/api/contracts/{self.contract.id}/document/',
            {'body': '<p>Yangi matn</p>'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn('Yangi matn', response.data['body'])
        document = ContractDocument.objects.get(contract=self.contract)
        self.assertEqual(document.versions.count(), 1)

    def test_document_upload_endpoint_removed(self):
        response = self.client.post(f'/api/contracts/{self.contract.id}/document/upload/')
        self.assertEqual(response.status_code, 404)

    def test_wopi_endpoint_removed(self):
        response = self.client.get('/api/wopi/files/1')
        self.assertEqual(response.status_code, 404)

    def test_body_placeholders_rendered_on_read_body_raw_keeps_them(self):
        """21-§3.2: `body` — qiymatlar bilan, `body_raw` bazadagi xom nusxa."""
        self.client.force_authenticate(self.sales)
        self.client.patch(
            f'/api/contracts/{self.contract.id}/document/',
            {'body': '<p>{{ contract.number }}</p>'}, format='json',
        )
        response = self.client.get(f'/api/contracts/{self.contract.id}/document/')
        self.assertIn(self.contract.number, response.data['body'])
        self.assertNotIn('{{', response.data['body'])
        self.assertIn('{{ contract.number }}', response.data['body_raw'])

    def test_attach_template_copies_body_and_flags(self):
        self.client.force_authenticate(self.sales)
        response = self.client.post(
            f'/api/contracts/{self.contract.id}/document/attach-template/',
            {'template': self.template.id}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)
        document = ContractDocument.objects.get(contract=self.contract)
        self.assertEqual(document.body, self.template.body)
        self.assertEqual(document.template_id, self.template.id)

    def test_attach_template_replaces_manual_edits(self):
        self.client.force_authenticate(self.sales)
        self.client.patch(
            f'/api/contracts/{self.contract.id}/document/',
            {'body': '<p>Qo\'lda yozilgan</p>'}, format='json',
        )
        self.client.post(
            f'/api/contracts/{self.contract.id}/document/attach-template/',
            {'template': self.template.id}, format='json',
        )
        document = ContractDocument.objects.get(contract=self.contract)
        self.assertNotIn("Qo'lda yozilgan", document.body)

    def test_inactive_template_cannot_be_attached(self):
        self.template.is_active = False
        self.template.save()
        self.client.force_authenticate(self.sales)
        response = self.client.post(
            f'/api/contracts/{self.contract.id}/document/attach-template/',
            {'template': self.template.id}, format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_submit_contract_requires_document_text(self):
        """21-§3.6: shablonsiz/matnsiz `submit` — 400 "matn bo'sh"."""
        self.client.force_authenticate(self.sales)
        Contract.objects.filter(pk=self.contract.pk).update(status=Contract.Status.DRAFT)
        response = self.client.post(f'/api/contracts/{self.contract.id}/submit/')
        self.assertEqual(response.status_code, 400)
        self.assertIn('bo\'sh', str(response.data))

    def test_submit_contract_succeeds_with_document_text(self):
        self.client.force_authenticate(self.sales)
        Contract.objects.filter(pk=self.contract.pk).update(status=Contract.Status.DRAFT)
        self.client.patch(
            f'/api/contracts/{self.contract.id}/document/',
            {'body': '<p>Matn</p>'}, format='json',
        )
        response = self.client.post(f'/api/contracts/{self.contract.id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)


class ContractTemplateTests(APITestCase):
    """21-§3.1: shablon CRUD — sales/admin yozadi, o'qish hammaga."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.admin = User.objects.create_user('adm', password='p', role=User.Role.ADMIN)

    def test_sales_creates_template(self):
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/contract-templates/', {
            'name': 'Standart', 'body': '<p>{{ contract.number }}</p>',
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)

    def test_bugalter_cannot_create_but_can_read(self):
        self.client.force_authenticate(self.bugalter)
        response = self.client.post('/api/contract-templates/', {
            'name': 'Standart', 'body': '<p>x</p>',
        }, format='json')
        self.assertEqual(response.status_code, 403)

        response = self.client.get('/api/contract-templates/')
        self.assertEqual(response.status_code, 200, response.data)

    def test_unknown_placeholder_rejected(self):
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/contract-templates/', {
            'name': 'Standart', 'body': '<p>{{ clientt.inn }}</p>',
        }, format='json')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('clientt.inn', str(response.data))

    def test_second_default_unsets_first(self):
        first = ContractTemplate.objects.create(
            name='Birinchi', body='<p>x</p>', is_default=True, created_by=self.sales,
        )
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/contract-templates/', {
            'name': 'Ikkinchi', 'body': '<p>y</p>', 'is_default': True,
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        first.refresh_from_db()
        self.assertFalse(first.is_default)
