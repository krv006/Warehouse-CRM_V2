from io import StringIO

from django.core.management import call_command

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.core.models import CompanyProfile, Notification
from apps.finance.models import CashCategory, CashTransaction
from apps.inventory.models import Product, StockReservation
from apps.procurement.models import Replenishment
from apps.sales.models import Contract, Lead


class WipeDataTests(APITestCase):
    """wipe_data: hammasi o'chadi — userlar, rekvizitlar, yacheykalar qoladi."""

    def test_wipe_clears_business_data_keeps_accounts(self):
        call_command('seed_demo', stdout=StringIO())
        self.assertTrue(Contract.objects.exists())
        users_before = User.objects.count()
        categories_before = CashCategory.objects.count()

        call_command('wipe_data', '--yes', stdout=StringIO())

        for model in (Contract, Lead, Client, Product, Replenishment,
                      CashTransaction, StockReservation, Notification):
            self.assertFalse(model.objects.exists(), model.__name__)

        # Qoladiganlar: akkauntlar, yacheykalar, rekvizitlar (sozlama)
        self.assertEqual(User.objects.count(), users_before)
        self.assertEqual(CashCategory.objects.count(), categories_before)
        self.assertEqual(CompanyProfile.objects.get().name, 'Ombor Servis MCHJ')

    def test_wipe_refuses_without_yes(self):
        call_command('seed_demo', stdout=StringIO())
        call_command('wipe_data', stdout=StringIO())  # --yes yo'q — hech nima o'chmaydi
        self.assertTrue(Contract.objects.exists())
