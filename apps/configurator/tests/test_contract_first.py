from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.configurator.models import Configuration, ConfigurationItem
from apps.core.models import CompanyProfile, Notification
from apps.inventory.models import (
    Product,
    ProductSpec,
    StockMovement,
    StockReservation,
    Warehouse,
)
from apps.inventory.services import apply_movement
from apps.sales.models import Contract, ContractDocument


class ContractFirstTests(APITestCase):
    """YANGI OQIM: zanjir `CFG → SHT → pul → mol` — shartnoma approve'da ochiladi."""

    def setUp(self):
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.admin = User.objects.create_user('adm', password='p', role=User.Role.ADMIN)
        self.supplier = User.objects.create_user('buy', password='p', role=User.Role.SUPPLIER)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.base = Product.objects.create(
            sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE,
            sale_price=Decimal('12000000'),
        )
        self.ram = Product.objects.create(
            sku='RAM-16', name='RAM 16', kind=Product.Kind.COMPONENT,
            sale_price=Decimal('1500000'),
        )
        ProductSpec.objects.create(
            product=self.base, component=self.ram, label='RAM', quantity=1,
        )
        apply_movement(
            product=self.ram, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('10'),
        )

    def _take_config(self, quantity=2):
        """ZVK (mijozli) -> engineer take — chernovik konfiguratsiya."""
        self.client.force_authenticate(self.sales)
        request_id = self.client.post('/api/configuration-requests/', {
            'text': f'{quantity} ta HP 880', 'base_product': self.base.id,
            'client': self.mijoz.id, 'quantity': quantity,
        }, format='json').data['id']
        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configuration-requests/{request_id}/take/')
        return Configuration.objects.get(pk=response.data['configuration'])

    def _approve(self, configuration):
        self.client.force_authenticate(self.engineer)
        self.client.post(f'/api/configurations/{configuration.id}/submit/')
        self.client.force_authenticate(self.sales)
        response = self.client.post(f'/api/configurations/{configuration.id}/approve/')
        configuration.refresh_from_db()
        return response

    def test_approve_opens_draft_contract(self):
        """B1: sales tasdig'i bilan draft shartnoma ochiladi — egasi zayavka sales'i."""
        configuration = self._take_config(quantity=2)
        response = self._approve(configuration)
        self.assertEqual(response.status_code, 200, response.data)

        contract = Contract.objects.get()
        self.assertEqual(contract.status, Contract.Status.DRAFT)
        self.assertEqual(contract.configuration, configuration)
        self.assertEqual(contract.created_by, self.sales)
        self.assertEqual(contract.client, self.mijoz)

        # Qator: hozircha bazaviy model (variant hali yig'ilmagan), partiya soni
        # 21-§1.3: narx endi doim qatorlar yig'indisi (RAM 1 x 1 500 000)
        item = contract.items.get()
        self.assertEqual(item.product, self.base)
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.unit_price, Decimal('1500000'))

        # B9: konfiguratsiya javobida shartnoma — front to'lov holatini ko'radi
        self.assertEqual(response.data['contract']['number'], contract.number)
        self.assertFalse(response.data['contract']['is_paid'])

    def test_approve_without_client_400(self):
        """B10: mijozsiz zanjirda shartnoma ochilmaydi — tasdiq ham o'tmaydi."""
        configuration = Configuration.objects.create(
            base_product=self.base, warehouse=self.warehouse,
            created_by=self.engineer, status=Configuration.Status.PENDING_SALES,
        )
        ConfigurationItem.objects.create(
            configuration=configuration, component=self.ram, label='RAM', quantity=1,
        )
        # Admin bilan: ZVK'siz konfiguratsiya sales ro'yxatiga tushmaydi
        self.client.force_authenticate(self.admin)
        response = self.client.post(f'/api/configurations/{configuration.id}/approve/')
        self.assertEqual(response.status_code, 400)
        self.assertIn('mijoz', str(response.data).lower())
        self.assertFalse(Contract.objects.exists())
        configuration.refresh_from_db()
        self.assertEqual(configuration.status, Configuration.Status.PENDING_SALES)

    def test_reapprove_reuses_contract(self):
        """Aylanma (§2.1): qayta tasdiqda ikkinchi shartnoma ochilmaydi."""
        configuration = self._take_config()
        self._approve(configuration)
        # change-quantity approved'ni pending_sales'ga qaytaradi — aylanma davom
        # (6-to'plam §4: sonni sales belgilaydi)
        self.client.force_authenticate(self.sales)
        self.client.post(
            f'/api/configurations/{configuration.id}/change-quantity/',
            {'quantity': 3, 'comment': 'Mijoz sonni oshirdi'}, format='json',
        )
        self.client.force_authenticate(self.sales)
        response = self.client.post(f'/api/configurations/{configuration.id}/approve/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(Contract.objects.count(), 1)

    def test_submit_blocked_without_price_and_request_prices_flow(self):
        """B2: narxsiz qator ko'rikka o'tmaydi; narx so'rovi TLD emas."""
        configuration = self._take_config()
        no_price = Product.objects.create(
            sku='CBL-X', name='Kabel X', kind=Product.Kind.COMPONENT,
        )
        ConfigurationItem.objects.create(
            configuration=configuration, component=no_price, label='KABEL', quantity=1,
        )
        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configurations/{configuration.id}/submit/')
        self.assertEqual(response.status_code, 400)
        self.assertIn('Kabel X', str(response.data['items']))

        # Narx so'rovi — eslatma MAHSULOTGA ishora qiladi (10-to'plam §1:
        # buyurtmachi konfiguratsiyani ko'ra olmaydi, mahsulot kartasi ochiq);
        # takrorida dublikat yo'q
        response = self.client.post(f'/api/configurations/{configuration.id}/request-prices/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['requested'], ['Kabel X'])

        # QOLGAN-ISHLAR-2 §7: hujjatning o'zi "so'ralganmi?" bilsin — tugma
        # ikkinchi marta bosilmasin (zararsiz, lekin chalkash)
        response = self.client.get(f'/api/configurations/{configuration.id}/')
        self.assertIsNotNone(response.data['price_requested_at'])

        self.client.post(f'/api/configurations/{configuration.id}/request-prices/')
        notes = Notification.objects.filter(user=self.supplier, is_read=False)
        self.assertEqual(notes.count(), 1)
        note = notes.get()
        self.assertIn('tannarx kerak', note.title)
        self.assertEqual(note.entity, 'Product')
        self.assertEqual(int(note.object_id), no_price.pk)

        # 10-§1: buyurtmachining doimiy ro'yxati — narxi kutilayotganlar
        self.client.force_authenticate(self.supplier)
        response = self.client.get('/api/products/?needs_price=true')
        skus = [row['sku'] for row in response.data['results']]
        self.assertEqual(skus, ['CBL-X'])

        # Buyurtmachi tannarxni mahsulot kartasida kiritadi (endi ruxsati bor)
        self.client.force_authenticate(self.supplier)
        response = self.client.patch(
            f'/api/products/{no_price.id}/', {'cost_price': '500000'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.data)

        # Qator to'ldi, buyurtmachi eslatmasi yopildi, sales xabar oldi
        item = configuration.items.get(component=no_price)
        self.assertEqual(item.unit_price, Decimal('500000'))
        self.assertFalse(
            Notification.objects.filter(user=self.supplier, is_read=False).exists(),
        )
        sales_note = Notification.objects.filter(
            user=self.sales, title__contains='narx keldi',
        )
        self.assertTrue(sales_note.exists())

        # Endi ko'rikka o'tadi
        self.client.force_authenticate(self.engineer)
        response = self.client.post(f'/api/configurations/{configuration.id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)

    def test_price_arrives_during_clarification(self):
        """10-to'plam §2: aniqlashtirish kutilayotganda ham narx qatorga tushadi."""
        configuration = self._take_config()
        no_price = Product.objects.create(
            sku='CBL-Y', name='Kabel Y', kind=Product.Kind.COMPONENT,
        )
        ConfigurationItem.objects.create(
            configuration=configuration, component=no_price, label='K', quantity=1,
        )
        self.client.force_authenticate(self.engineer)
        self.client.post(f'/api/configurations/{configuration.id}/request-prices/')
        self.client.post(
            f'/api/configurations/{configuration.id}/ask-sales/',
            {'comment': 'Qaysi rang kerak?'}, format='json',
        )
        configuration.refresh_from_db()
        self.assertEqual(
            configuration.status, Configuration.Status.PENDING_CLARIFICATION,
        )
        self.client.force_authenticate(self.supplier)
        self.client.patch(
            f'/api/products/{no_price.id}/', {'cost_price': '250000'}, format='json',
        )
        item = configuration.items.get(component=no_price)
        self.assertEqual(item.unit_price, Decimal('250000'))

    def test_request_prices_blocked_after_approval(self):
        """10-to'plam §2: narx allaqachon shartnomaga kirib bo'lgan — 400."""
        configuration = self._take_config()
        self._approve(configuration)
        self.client.force_authenticate(self.engineer)
        response = self.client.post(
            f'/api/configurations/{configuration.id}/request-prices/',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('shartnomaga kirib', str(response.data['detail']))

    def test_contract_reserves_nothing_until_ready(self):
        """B5.1: CFG tayyor bo'lmaguncha shartnoma bron qo'ymaydi — mol CFG da."""
        configuration = self._take_config()
        self._approve(configuration)
        contract = Contract.objects.get()
        self.client.force_authenticate(self.sales)
        ContractDocument.objects.update_or_create(contract=contract, defaults={'body': '<p>x</p>'})
        response = self.client.post(f'/api/contracts/{contract.id}/submit/')
        self.assertEqual(response.status_code, 200, response.data)

        self.assertFalse(
            StockReservation.objects.filter(contract=contract).exists(),
        )
        # Molni konfiguratsiyaning yumshoq broni ushlab turibdi
        reservation = StockReservation.objects.get(configuration=configuration)
        self.assertEqual(reservation.kind, StockReservation.Kind.SOFT)

    def test_payment_hardens_configuration_reservation(self):
        """B5.2/3: boshlang'ich to'lov — bron yumshoqdan qattiqqa, muddatsiz."""
        configuration = self._take_config(quantity=2)
        self._approve(configuration)
        contract = Contract.objects.get()
        self.client.force_authenticate(self.sales)
        ContractDocument.objects.update_or_create(contract=contract, defaults={'body': '<p>x</p>'})
        self.client.post(f'/api/contracts/{contract.id}/submit/')
        # 12-§1: sales -> bugalter -> admin -> Didox -> to'lov
        self.client.force_authenticate(self.bugalter)
        self.client.post(f'/api/contracts/{contract.id}/approve/')
        self.client.force_authenticate(self.admin)
        self.client.post(f'/api/contracts/{contract.id}/approve/')
        self.client.force_authenticate(self.bugalter)
        self.client.post(f'/api/contracts/{contract.id}/send-didox/', {
            'didox_number': 'DDX-77',
        }, format='json')
        self.client.post(f'/api/contracts/{contract.id}/confirm-didox/')
        response = self.client.post(f'/api/contracts/{contract.id}/confirm-payment/')
        self.assertEqual(response.status_code, 200, response.data)

        reservation = StockReservation.objects.get(
            configuration=configuration, status=StockReservation.Status.ACTIVE,
        )
        self.assertEqual(reservation.kind, StockReservation.Kind.HARD)
        self.assertIsNone(reservation.expires_at)  # pul kelgan mol muddatsiz band
        configuration.refresh_from_db()
        self.assertTrue(configuration.is_paid)

        # Engineer "ish boshlanadi" xabarini oladi
        self.assertTrue(
            Notification.objects.filter(
                user=self.engineer, title__contains="to'lov keldi",
            ).exists(),
        )

    def test_markup_applied_when_only_cost_price(self):
        """§6-B: sotuv narxi yo'q — tannarx + ustama; 0 bo'lsa eski xulq."""
        product = Product.objects.create(
            sku='SSD-2', name='SSD 2', kind=Product.Kind.COMPONENT,
            cost_price=Decimal('1000000'),
        )
        self.assertEqual(product.stock_price, Decimal('1000000'))  # ustama 0

        profile = CompanyProfile.load()
        profile.markup_percent = Decimal('20')
        profile.save()
        self.assertEqual(product.stock_price, Decimal('1200000.00'))
