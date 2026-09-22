from decimal import Decimal

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.configurator.models import Configuration, ConfigurationRequest
from apps.configurator.services import chain_open_replenishment
from apps.inventory.models import Product, ProductSpec, StockMovement, Warehouse
from apps.inventory.services import apply_movement
from apps.procurement.models import Replenishment
from apps.sales.models import Contract
from apps.sales.services import archive_completed_chain


class MultiModelContractTests(APITestCase):
    """12-§2 (C): bitta savdoda bir nechta model — bitta shartnoma, N konfiguratsiya.

    Mijoz bir suhbatda ikki xil narsa so'raydi: bitta savdo (shartnoma, Didox,
    to'lov, muddat), lekin ikkita muhandislik ishi (har biri o'z konfiguratsiyasi,
    ehtimol ikki xil engineer).
    """

    def setUp(self):
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
        self.engineer2 = User.objects.create_user('eng2', password='p', role=User.Role.ENGINEER)
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.sales2 = User.objects.create_user('sal2', password='p', role=User.Role.SALES)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.mijoz2 = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Vali Aliyev',
            passport='AA1112224', jshshir='11112222333345', phone='+998900000002',
        )
        self.warehouse = Warehouse.objects.create(name='Asosiy ombor')
        self.hp = Product.objects.create(
            sku='HP-880', name='HP 880', kind=Product.Kind.MACHINE,
            sale_price=Decimal('12000000'),
        )
        self.dell = Product.objects.create(
            sku='DELL-7010', name='Dell OptiPlex 7010', kind=Product.Kind.MACHINE,
            sale_price=Decimal('10000000'),
        )
        self.ram = Product.objects.create(
            sku='RAM-16', name='RAM 16', kind=Product.Kind.COMPONENT,
            sale_price=Decimal('1500000'),
        )
        # Har ikkala model ham shu komponentdan tarkib topadi — `take`
        # avtomatik ConfigurationItem yozadi, submit shu bilan o'tadi
        ProductSpec.objects.create(
            product=self.hp, component=self.ram, label='RAM', quantity=1,
        )
        ProductSpec.objects.create(
            product=self.dell, component=self.ram, label='RAM', quantity=1,
        )
        apply_movement(
            product=self.ram, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('10'),
        )

    def _take_config(self, engineer, base_product, quantity=1, client=None, sales_user=None):
        self.client.force_authenticate(sales_user or self.sales)
        request_id = self.client.post('/api/configuration-requests/', {
            'text': f'{quantity} ta {base_product.name}', 'base_product': base_product.id,
            'client': (client or self.mijoz).id, 'quantity': quantity,
        }, format='json').data['id']
        self.client.force_authenticate(engineer)
        response = self.client.post(f'/api/configuration-requests/{request_id}/take/')
        configuration = Configuration.objects.get(pk=response.data['configuration'])
        self.client.post(f'/api/configurations/{configuration.id}/submit/')
        return configuration

    def _approve(self, configuration, contract=None, sales_user=None):
        self.client.force_authenticate(sales_user or self.sales)
        body = {'contract': contract.id} if contract else {}
        response = self.client.post(
            f'/api/configurations/{configuration.id}/approve/', body, format='json',
        )
        configuration.refresh_from_db()
        return response

    def test_second_model_attaches_to_existing_draft_contract(self):
        """C2: yangi shartnoma ochilmaydi — mavjud qoralamaga qator qo'shiladi."""
        cfg_a = self._take_config(self.engineer, self.hp)
        self._approve(cfg_a)
        contract = Contract.objects.get()

        cfg_b = self._take_config(self.engineer2, self.dell)
        response = self._approve(cfg_b, contract=contract)
        self.assertEqual(response.status_code, 200, response.data)

        self.assertEqual(Contract.objects.count(), 1)
        contract.refresh_from_db()
        self.assertEqual(contract.items.count(), 2)
        self.assertEqual(contract.total_amount, contract.items_total_with_vat)

        cfg_b.refresh_from_db()
        self.assertEqual(cfg_b.active_contract, contract)
        item_b = contract.items.get(configuration=cfg_b)
        self.assertEqual(item_b.product, self.dell)

        # QOLGAN-ISHLAR #4: front qatorlarni raqam bilan ajrata olsin
        self.client.force_authenticate(self.sales)
        response = self.client.get(f'/api/contracts/{contract.id}/')
        numbers = {row['configuration_number'] for row in response.data['items']}
        self.assertEqual(numbers, {cfg_a.number, cfg_b.number})

    def test_cannot_attach_to_non_draft_contract(self):
        """Bugalterga ketgan (draft emas) shartnomaga yangi model qo'shilmaydi."""
        cfg_a = self._take_config(self.engineer, self.hp)
        self._approve(cfg_a)
        contract = Contract.objects.get()
        self.client.force_authenticate(self.sales)
        self.client.post(f'/api/contracts/{contract.id}/submit/')

        cfg_b = self._take_config(self.engineer2, self.dell)
        response = self._approve(cfg_b, contract=contract)
        self.assertEqual(response.status_code, 400)
        contract.refresh_from_db()
        self.assertEqual(contract.items.count(), 1)

    def test_cannot_attach_with_different_client(self):
        """Boshqa mijozning shartnomasiga model qo'shib bo'lmaydi."""
        cfg_a = self._take_config(self.engineer, self.hp)
        self._approve(cfg_a)
        contract = Contract.objects.get()

        cfg_b = self._take_config(self.engineer2, self.dell, client=self.mijoz2)
        response = self._approve(cfg_b, contract=contract)
        self.assertEqual(response.status_code, 400)

    def test_cannot_attach_someone_elses_contract(self):
        """Boshqa sales'ning shartnomasiga (admin bo'lmasa) qo'shib bo'lmaydi."""
        cfg_a = self._take_config(self.engineer, self.hp, sales_user=self.sales)
        self._approve(cfg_a, sales_user=self.sales)
        contract = Contract.objects.get()

        cfg_b = self._take_config(self.engineer2, self.dell, sales_user=self.sales2)
        response = self._approve(cfg_b, contract=contract, sales_user=self.sales2)
        self.assertEqual(response.status_code, 400)

    def test_active_contract_resolves_via_item_for_second_model(self):
        """`active_contract`: birinchi model FK orqali, ikkinchisi qator orqali topiladi."""
        cfg_a = self._take_config(self.engineer, self.hp)
        self._approve(cfg_a)
        contract = Contract.objects.get()
        cfg_b = self._take_config(self.engineer2, self.dell)
        self._approve(cfg_b, contract=contract)
        cfg_b.refresh_from_db()

        # Ikkinchi model Contract.configuration orqali ulanmagan
        self.assertNotEqual(contract.configuration_id, cfg_b.id)
        # ...lekin active_contract baribir topadi (qator orqali)
        self.assertEqual(cfg_b.active_contract, contract)
        self.assertTrue(cfg_b.is_paid is False)  # hali to'lanmagan, lekin xato bermaydi

    def test_tld_for_one_model_does_not_block_the_other(self):
        """C4/11-§1: A modeli uchun ochilgan TLD B modelini bloklamaydi."""
        cfg_a = self._take_config(self.engineer, self.hp)
        self._approve(cfg_a)
        contract = Contract.objects.get()
        cfg_b = self._take_config(self.engineer2, self.dell)
        self._approve(cfg_b, contract=contract)
        cfg_a.refresh_from_db()
        cfg_b.refresh_from_db()

        Replenishment.objects.create(
            warehouse=self.warehouse, configuration=cfg_a, created_by=self.engineer,
        )
        # A modelining o'zi ikkinchi marta ocholmaydi
        self.assertIsNotNone(chain_open_replenishment(configuration=cfg_a))
        # ...lekin B modeli erkin
        self.assertIsNone(chain_open_replenishment(configuration=cfg_b))

    def test_archive_completed_chain_archives_both_requests(self):
        """B7: shartnoma yopilganda IKKALA modelning zayavkasi arxivlanadi."""
        cfg_a = self._take_config(self.engineer, self.hp)
        self._approve(cfg_a)
        contract = Contract.objects.get()
        cfg_b = self._take_config(self.engineer2, self.dell)
        self._approve(cfg_b, contract=contract)

        request_a = ConfigurationRequest.objects.get(configuration=cfg_a)
        request_b = ConfigurationRequest.objects.get(configuration=cfg_b)
        request_a.status = ConfigurationRequest.Status.DONE
        request_a.save()
        request_b.status = ConfigurationRequest.Status.DONE
        request_b.save()

        Contract.objects.filter(pk=contract.pk).update(status=Contract.Status.COMPLETED)
        contract.refresh_from_db()
        archive_completed_chain(contract)

        request_a.refresh_from_db()
        request_b.refresh_from_db()
        self.assertEqual(request_a.status, ConfigurationRequest.Status.ARCHIVED)
        self.assertEqual(request_b.status, ConfigurationRequest.Status.ARCHIVED)
