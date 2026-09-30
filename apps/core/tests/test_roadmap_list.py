from datetime import timedelta
from decimal import Decimal

from django.utils.timezone import now

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.configurator.models import Configuration, ConfigurationRequest
from apps.inventory.models import (
    Product,
    ProductSpec,
    StockMovement,
    Warehouse,
)
from apps.inventory.services import apply_movement
from apps.sales.models import Contract, ContractDocument


class RoadmapListTests(APITestCase):
    """7-to'plam §1: bosh sahifa uchun zanjirlar ro'yxati — GET /roadmaps/."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.engineer = User.objects.create_user('eng', password='p', role=User.Role.ENGINEER)
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
            sale_price=Decimal('700000'),
        )
        ProductSpec.objects.create(
            product=self.base, component=self.ram, label='RAM', quantity=1,
        )
        apply_movement(
            product=self.ram, warehouse=self.warehouse,
            type=StockMovement.Type.IN, quantity=Decimal('10'),
        )

        # A zanjiri: to'lov kutilmoqda (joriy — prepayment, bugalter)
        self.request_a = self._chain_to_waiting_payment()
        # B zanjiri: chernovik (joriy — submitted, engineer)
        self.request_b = self._chain_draft()
        # C zanjiri: bekor qilingan (yopiq)
        self.request_c = self._chain_draft()
        self.client.force_authenticate(self.sales)
        self.client.post(
            f'/api/configuration-requests/{self.request_c.id}/cancel/',
            {'reason': 'Mijoz voz kechdi'}, format='json',
        )

    def _zvk(self, text):
        self.client.force_authenticate(self.sales)
        request_id = self.client.post('/api/configuration-requests/', {
            'text': text, 'base_product': self.base.id,
            'client': self.mijoz.id, 'quantity': 1,
        }, format='json').data['id']
        return ConfigurationRequest.objects.get(pk=request_id)

    def _chain_draft(self):
        request_obj = self._zvk('Chernovik zanjiri')
        self.client.force_authenticate(self.engineer)
        self.client.post(f'/api/configuration-requests/{request_obj.id}/take/')
        request_obj.refresh_from_db()
        return request_obj

    def _chain_to_waiting_payment(self):
        request_obj = self._chain_draft()
        configuration = request_obj.configuration
        self.client.post(f'/api/configurations/{configuration.id}/submit/')
        self.client.force_authenticate(self.sales)
        self.client.post(f'/api/configurations/{configuration.id}/approve/')
        configuration.refresh_from_db()
        contract = configuration.active_contract
        ContractDocument.objects.update_or_create(contract=contract, defaults={'body': '<p>x</p>'})
        self.client.post(f'/api/contracts/{contract.id}/submit/')
        # 12-§1: sales -> bugalter -> admin -> Didox -> to'lov
        self.client.force_authenticate(self.bugalter)
        self.client.post(f'/api/contracts/{contract.id}/approve/')
        contract.refresh_from_db()
        if contract.status == Contract.Status.PENDING_ADMIN:
            self.client.force_authenticate(self.admin)
            self.client.post(f'/api/contracts/{contract.id}/approve/')
            self.client.force_authenticate(self.bugalter)
        self.client.post(
            f'/api/contracts/{contract.id}/send-didox/',
            {'didox_number': 'DDX-1'}, format='json',
        )
        self.client.post(f'/api/contracts/{contract.id}/confirm-didox/')
        request_obj.refresh_from_db()
        return request_obj

    def _numbers(self, response):
        return [row['request']['number'] for row in response.data['results']]

    def test_bugalter_sees_chain_waiting_on_his_role(self):
        """Egasi emas, lekin navbat unda — ro'yxatga tushadi (asosiy shart)."""
        self.client.force_authenticate(self.bugalter)
        response = self.client.get('/api/roadmaps/')
        self.assertEqual(response.status_code, 200, response.data)
        numbers = self._numbers(response)
        self.assertIn(self.request_a.number, numbers)     # joriy — prepayment
        self.assertNotIn(self.request_b.number, numbers)  # chernovik — unda emas
        self.assertNotIn(self.request_c.number, numbers)  # yopiq

    def test_supplier_sees_nothing_until_his_turn(self):
        self.client.force_authenticate(self.supplier)
        response = self.client.get('/api/roadmaps/')
        self.assertEqual(response.data['count'], 0)

    def test_engineer_sees_own_chains(self):
        """Egasi sifatida ikkala ochiq zanjirni ham ko'radi."""
        self.client.force_authenticate(self.engineer)
        numbers = self._numbers(self.client.get('/api/roadmaps/'))
        self.assertIn(self.request_a.number, numbers)
        self.assertIn(self.request_b.number, numbers)
        self.assertNotIn(self.request_c.number, numbers)

    def test_results_match_detail_roadmap_shape(self):
        """results[i] — detal roadmap javobi bilan bir xil: 20 qadam, pul yo'q."""
        self.client.force_authenticate(self.admin)
        response = self.client.get('/api/roadmaps/')
        row = next(
            r for r in response.data['results']
            if r['request']['number'] == self.request_a.number
        )
        self.assertEqual(len(row['steps']), 20)
        self.assertEqual(row['current_key'], 'prepayment')
        self.assertEqual(row['client_name'], 'Ali Valiyev')
        raw = str(response.data)
        for token in ('total_amount', 'prepayment_amount', 'unit_price', 'balance'):
            self.assertNotIn(token, raw)

    def test_overdue_chain_comes_first_and_limit_works(self):
        """Tartib: muddatdan o'tgan birinchi; limit ishlaydi."""
        # A zanjiri shartnomasini 6 kun "turib qolgan" qilamiz — danger
        contract = self.request_a.configuration.active_contract
        Contract.objects.filter(pk=contract.pk).update(
            status_changed_at=now() - timedelta(days=6),
        )
        self.client.force_authenticate(self.admin)
        numbers = self._numbers(self.client.get('/api/roadmaps/'))
        self.assertEqual(numbers[0], self.request_a.number)

        response = self.client.get('/api/roadmaps/?limit=1')
        self.assertEqual(len(response.data['results']), 1)
        self.assertGreaterEqual(response.data['count'], 2)  # count — limitgacha

    def test_actor_keeps_chain_after_turn_passes(self):
        """10-§5: qo'l tekkizgan odam zanjirni yopilguncha ko'radi.

        Bugalter to'lovni o'tkazdi — navbat engineerga o'tdi, lekin zanjir
        bugalterdan yo'qolmaydi (avval suratga qarab yo'qolardi).
        """
        contract = self.request_a.configuration.active_contract
        self.client.force_authenticate(self.bugalter)
        response = self.client.post(
            f'/api/contracts/{contract.id}/confirm-payment/',
        )
        self.assertEqual(response.status_code, 200, response.data)
        # Joriy qadam endi bugalterda emas
        roadmap = self.client.get(
            f'/api/contracts/{contract.id}/roadmap/',
        ).data
        self.assertNotIn(roadmap['current_key'], ('prepayment', 'approved_waiting'))

        numbers = self._numbers(self.client.get('/api/roadmaps/'))
        self.assertIn(self.request_a.number, numbers)

    def test_engineer_pool_narrows_after_take(self):
        """10-§5 hovuz: yangi zayavkani hamma engineer ko'radi, olingach —
        faqat oluvchisi (rol bo'yicha keng ko'rinish yopildi)."""
        engineer2 = User.objects.create_user(
            'eng2', password='p', role=User.Role.ENGINEER,
        )
        fresh = self._zvk('Hovuz testi')  # hali hech kim olmagan
        self.client.force_authenticate(engineer2)
        numbers = self._numbers(self.client.get('/api/roadmaps/'))
        self.assertIn(fresh.number, numbers)
        # B zanjiri eng1 tomonidan olingan — eng2 uni KO'RMAYDI
        self.assertNotIn(self.request_b.number, numbers)
        # Oluvchining o'zida esa turibdi
        self.client.force_authenticate(self.engineer)
        numbers = self._numbers(self.client.get('/api/roadmaps/'))
        self.assertIn(self.request_b.number, numbers)

    def test_supplier_pool_when_tld_on_the_way(self):
        """10-§5+§6: TLD buyurtmachi bosqichida — hovuzdagi buyurtmachi ko'radi."""
        from apps.procurement.models import Replenishment

        contract = self.request_a.configuration.active_contract
        Contract.objects.filter(pk=contract.pk).update(
            status=Contract.Status.ACTIVE,
        )
        Replenishment.objects.create(
            warehouse=self.warehouse,
            configuration=self.request_a.configuration,
            status=Replenishment.Status.ORDERED,  # §6: egasi buyurtmachi
            created_by=self.engineer,
        )
        self.client.force_authenticate(self.supplier)
        numbers = self._numbers(self.client.get('/api/roadmaps/'))
        self.assertIn(self.request_a.number, numbers)

    def test_state_closed_returns_cancelled_chain(self):
        self.client.force_authenticate(self.admin)
        numbers = self._numbers(self.client.get('/api/roadmaps/?state=closed'))
        self.assertEqual(numbers, [self.request_c.number])
        numbers = self._numbers(self.client.get('/api/roadmaps/?state=all'))
        self.assertIn(self.request_c.number, numbers)
