from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.accounts.models import User
from apps.clients.models import Client


class SeedClientsTests(TestCase):
    """seed_clients komandasi demo buyurtmachilarni yaratadi."""

    def _run(self):
        out = StringIO()
        call_command('seed_clients', stdout=out)
        return out.getvalue()

    def test_creates_two_of_each_type(self):
        self._run()
        self.assertEqual(Client.objects.filter(type=Client.Type.INDIVIDUAL).count(), 2)
        self.assertEqual(Client.objects.filter(type=Client.Type.LEGAL).count(), 2)

    def test_required_fields_are_filled(self):
        self._run()
        individual = Client.objects.filter(type=Client.Type.INDIVIDUAL).first()
        legal = Client.objects.filter(type=Client.Type.LEGAL).first()
        for field in ['full_name', 'passport', 'jshshir', 'phone']:
            self.assertTrue(getattr(individual, field), field)
        for field in ['company_name', 'inn', 'jshshir', 'mfo', 'bank_name',
                      'account_number', 'director_name', 'phone']:
            self.assertTrue(getattr(legal, field), field)

    def test_second_run_does_not_duplicate(self):
        self._run()
        self._run()
        self.assertEqual(Client.objects.count(), 4)

    def test_created_by_is_sales_when_available(self):
        sales = User.objects.create_user('sales1', password='p', role=User.Role.SALES)
        self._run()
        self.assertEqual(Client.objects.first().created_by, sales)
