from datetime import date
from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.configurator.models import (
    Act,
    Configuration,
    ConfigurationItem,
    ConfigurationRequest,
)
from apps.inventory.models import Product, StockMovement, Warehouse
from apps.inventory.services import apply_movement
from apps.sales.models import Contract, Lead


class ChainClosureTests(APITestCase):
    """§10.8: zanjir oxirida hujjatlar yopiladi — Lead, ZVK, CFG."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.admin = User.objects.create_user('adm', password='p', role=User.Role.ADMIN)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.product = Product.objects.create(
            sku='ADS-1', name='adas', sale_price=Decimal('5000000'),
        )
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        apply_movement(
            product=self.product, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('5'),
        )

    def test_lead_auto_linked_on_contract_create(self):
        """Shartnoma tuzilganda mijozning ochiq kelishuvi unga bog'lanadi."""
        lead = Lead.objects.create(
            client=self.mijoz, title='HP 880 kelishuvi',
            stage=Lead.Stage.VERBAL, created_by=self.sales,
        )
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/contracts/', {
            'client': self.mijoz.id,
            'items': [{'product': self.product.id, 'quantity': 1, 'unit_price': '5000000'}],
        }, format='json')
        self.assertEqual(response.status_code, 201, response.data)

        lead.refresh_from_db()
        self.assertEqual(lead.stage, Lead.Stage.CONTRACT)
        self.assertEqual(lead.contract_id, response.data['id'])

    def test_configuration_sold_and_request_archived(self):
        """YANGI OQIM: approve'da SHT -> to'lov -> yig'ish -> finalize (`sold`)
        -> yetkazish (`completed`) — ZVK faqat shu yerda `archived`."""
        configuration = Configuration.objects.create(
            base_product=Product.objects.create(
                sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE,
            ),
            warehouse=self.warehouse, created_by=self.engineer,
        )
        ConfigurationItem.objects.create(
            configuration=configuration, component=self.product,
            label='ADS', quantity=1, unit_price=Decimal('5000000'),
        )
        request_obj = ConfigurationRequest.objects.create(
            client=self.mijoz, text='HP 880', created_by=self.sales,
            configuration=configuration, status=ConfigurationRequest.Status.DONE,
        )
        act = Act.objects.create(number='ACT-1', title='ACT', issued_at=date.today())

        # Engineer submit -> sales approve — SHU YERDA shartnoma ochiladi (B1)
        url = f'/api/configurations/{configuration.id}'
        self.client.force_authenticate(self.engineer)
        self.client.post(f'{url}/submit/')
        self.client.force_authenticate(self.sales)  # zayavka egasi tasdiqlaydi
        response = self.client.post(f'{url}/approve/')
        self.assertEqual(response.status_code, 200, response.data)
        contract_id = response.data['contract']['id']

        # ZVK hali arxivda EMAS — u zanjir umurtqasi (B7, §3.5)
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, ConfigurationRequest.Status.DONE)

        # Pul: sales submit -> bugalter -> admin -> Didox -> to'liq to'lov (12-§1)
        self.client.post(f'/api/contracts/{contract_id}/submit/')
        self.client.force_authenticate(self.bugalter)
        self.client.post(f'/api/contracts/{contract_id}/approve/')
        self.client.force_authenticate(self.admin)
        self.client.post(f'/api/contracts/{contract_id}/approve/')
        self.client.force_authenticate(self.bugalter)
        self.client.post(
            f'/api/contracts/{contract_id}/send-didox/',
            {'didox_number': 'DDX-1'}, format='json',
        )
        self.client.post(f'/api/contracts/{contract_id}/confirm-didox/')
        total = Contract.objects.get(pk=contract_id).total_amount
        response = self.client.post(
            f'/api/contracts/{contract_id}/confirm-payment/',
            {'amount': str(total)}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)

        # Mol endi tayyorlanadi: yig'ish -> finalize — CFG `sold` (B7)
        self.client.force_authenticate(self.engineer)
        self.client.post(f'{url}/assemble/')
        response = self.client.post(f'{url}/finalize/', {'act': act.id}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        configuration.refresh_from_db()
        self.assertEqual(configuration.status, Configuration.Status.SOLD)

        # 21-§1.3: shartnoma qatori bazaviy modelda qoladi — alohida
        # katalog yozuvi (variant) endi yaratilmaydi
        contract = Contract.objects.get(pk=contract_id)
        self.assertEqual(contract.items.get().product, configuration.base_product)
        self.assertIsNone(configuration.variant)

        # 20-§3: finalize ACT ni avtomatik bugalter tasdig'iga yuboradi —
        # ship shu tasdiqni kutadi
        act.refresh_from_db()
        self.assertEqual(act.status, Act.Status.PENDING_BUGALTER)
        self.client.force_authenticate(self.bugalter)
        response = self.client.post(f'/api/acts/{act.id}/approve/')
        self.assertEqual(response.status_code, 200, response.data)

        # Yetkazish — shartnoma yopiladi, ZVK endi arxivga o'tadi (B7)
        # 11-§3: sales (egasi) yetkazadi
        self.client.force_authenticate(self.sales)
        response = self.client.post(f'/api/contracts/{contract_id}/ship/')
        self.assertEqual(response.status_code, 200, response.data)
        contract.refresh_from_db()
        self.assertEqual(contract.status, Contract.Status.COMPLETED)
        request_obj.refresh_from_db()
        self.assertEqual(request_obj.status, ConfigurationRequest.Status.ARCHIVED)
