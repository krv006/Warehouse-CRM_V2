from decimal import Decimal

from django.utils.timezone import now

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.core.models import Notification
from apps.finance.models import CashTransaction
from apps.finance.services import record_transaction
from apps.inventory.models import Product
from apps.procurement.models import Replenishment, ReplenishmentItem
from apps.purchases.models import Purchase


class PayFreezeTests(APITestCase):
    """§10.5/§10.9/§10.10: to'lovdan keyin raqamlar muzlaydi va kassa bog'lanadi."""

    def setUp(self):
        from apps.inventory.services import main_warehouse

        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.admin = User.objects.create_user('adm', password='p', role=User.Role.ADMIN)
        self.buyurtmachi = User.objects.create_user(
            'buy', password='p', role=User.Role.SUPPLIER,
        )
        self.warehouse = main_warehouse()
        self.gpu = Product.objects.create(sku='GPU-1', name='GPU')
        record_transaction(code='ustav_in', amount=Decimal('3000000'), occurred_at=now())

        self.replenishment = Replenishment.objects.create(
            warehouse=self.warehouse, status=Replenishment.Status.APPROVED,
            created_by=self.buyurtmachi,
        )
        ReplenishmentItem.objects.create(
            replenishment=self.replenishment, product=self.gpu,
            quantity=1, unit_price=Decimal('4000000'),
        )
        self.client.force_authenticate(self.bugalter)

    def _pay(self):
        return self.client.post(f'/api/replenishments/{self.replenishment.id}/pay/')

    def test_shortfall_is_frozen_after_pay(self):
        """To'lovdan keyin shortfall kassaga qarab 'o'ynamaydi' — muzlatilgani turadi."""
        response = self._pay()
        self.assertEqual(response.status_code, 200, response.data)
        self.replenishment.refresh_from_db()
        # 4 mln kerak, kassada 3 mln edi -> 1 mln qarz, shu muzlaydi
        self.assertEqual(self.replenishment.debt_amount, Decimal('1000000.00'))
        self.assertEqual(self.replenishment.shortfall, Decimal('1000000.00'))

        # Kassaga katta kirim tushdi — muzlatilgan qarz o'zgarmasligi kerak
        record_transaction(code='ustav_in', amount=Decimal('50000000'), occurred_at=now())
        self.assertEqual(self.replenishment.shortfall, Decimal('1000000.00'))

    def test_cash_transaction_linked_and_categorized(self):
        """§10.9: chiqim TLD ga FK bilan bog'lanadi, yacheyka hujjat turidan."""
        self._pay()
        expense = CashTransaction.objects.get(replenishment=self.replenishment,
                                              category__code='contract_invoice')
        self.assertEqual(expense.amount, Decimal('3000000'))

    def test_debt_notification_targeted_not_global(self):
        """§10.10: qarz xabari user'siz emas — faqat bugalter va adminga."""
        self._pay()
        notes = Notification.objects.filter(title__contains='qarzga')
        self.assertTrue(notes.exists())
        self.assertFalse(notes.filter(user__isnull=True).exists())
        self.assertTrue(notes.filter(user=self.bugalter).exists())
        self.assertTrue(notes.filter(user=self.admin).exists())

    def test_cash_hidden_from_supplier_in_serializer(self):
        """§10.4: kassa qoldig'i buyurtmachiga sizmaydi."""
        self.client.force_authenticate(self.buyurtmachi)
        response = self.client.get(f'/api/replenishments/{self.replenishment.id}/')
        self.assertIsNone(response.data['cash_available'])
        self.assertIsNone(response.data['shortfall'])

        self.client.force_authenticate(self.bugalter)
        response = self.client.get(f'/api/replenishments/{self.replenishment.id}/')
        self.assertIsNotNone(response.data['cash_available'])


class AutoKirTests(APITestCase):
    """§4.3: TLD receive KIR hujjatini o'zi ochadi — kirim bitta yo'ldan."""

    def setUp(self):
        from apps.inventory.services import main_warehouse

        self.bugalter = User.objects.create_user('bug', password='p', role=User.Role.BUGALTER)
        self.warehouse = main_warehouse()
        self.gpu = Product.objects.create(sku='GPU-1', name='GPU')
        self.replenishment = Replenishment.objects.create(
            warehouse=self.warehouse, status=Replenishment.Status.ORDERED,
            supplier='Etuf MCHJ', created_by=self.bugalter,
        )
        ReplenishmentItem.objects.create(
            replenishment=self.replenishment, product=self.gpu,
            quantity=2, unit_price=Decimal('4000000'),
        )
        self.client.force_authenticate(self.bugalter)

    def test_receive_opens_received_kir(self):
        response = self.client.post(
            f'/api/replenishments/{self.replenishment.id}/receive/',
        )
        self.assertEqual(response.status_code, 200, response.data)

        purchase = Purchase.objects.get(replenishment=self.replenishment)
        self.assertEqual(purchase.status, Purchase.Status.RECEIVED)
        self.assertEqual(purchase.supplier, 'Etuf MCHJ')
        item = purchase.items.get()
        self.assertEqual(item.product, self.gpu)
        self.assertEqual(item.quantity, Decimal('2'))
        # Javobda ham ko'rinadi — front havola qiladi
        self.assertEqual(response.data['purchase']['number'], purchase.number)
        # KIR kassaga hech narsa yozmagan (pul TLD pay'da chiqqan)
        self.assertFalse(CashTransaction.objects.filter(purchase=purchase).exists())
        # Bugalterga hujjat biriktirish eslatmasi
        self.assertTrue(
            Notification.objects.filter(
                user=self.bugalter, entity='Purchase', object_id=str(purchase.pk),
            ).exists()
        )

    def test_auto_kir_cannot_be_received_again(self):
        """TLD dan ochilgan KIR receive qilinmaydi — ikkinchi kirim yo'q."""
        self.client.post(f'/api/replenishments/{self.replenishment.id}/receive/')
        purchase = Purchase.objects.get(replenishment=self.replenishment)
        response = self.client.post(f'/api/purchases/{purchase.id}/receive/')
        self.assertEqual(response.status_code, 400)
        self.assertIn('TLD', str(response.data))
