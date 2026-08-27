from datetime import timedelta
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.utils.timezone import localdate, now
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.core.models import ActivityLog, Notification
from apps.finance.models import Loan
from apps.finance.services import ensure_default_categories, record_transaction
from apps.sales.models import Contract


class DashboardTests(APITestCase):
    """Admin dashboardi kassa, kirim, sotuv va muddatlarni ko'rsatadi."""

    def setUp(self):
        ensure_default_categories()
        self.admin = User.objects.create_user('admin', password='p', role=User.Role.ADMIN)
        self.client.force_authenticate(self.admin)
        record_transaction(code='sale', amount=Decimal('10000000'), occurred_at=now())
        record_transaction(code='rent', amount=Decimal('2000000'), occurred_at=now())

    def test_dashboard_sections(self):
        response = self.client.get('/api/dashboard/')
        self.assertEqual(response.status_code, 200)
        for section in ['kassa', 'kirim', 'sales', 'clients', 'ombor', 'deadlines']:
            self.assertIn(section, response.data)
        self.assertEqual(response.data['kassa']['balance'], Decimal('8000000'))


class ActivityLogTests(APITestCase):
    """Kim nima qilgani yozib boriladi va faqat adminga ko'rinadi."""

    def setUp(self):
        self.sales = User.objects.create_user('sales', password='p', role=User.Role.SALES)
        self.admin = User.objects.create_user('admin', password='p', role=User.Role.ADMIN)

    def test_create_writes_log(self):
        self.client.force_authenticate(self.sales)
        response = self.client.post('/api/clients/', {
            'type': Client.Type.INDIVIDUAL,
            'full_name': 'Ali Valiyev',
            'passport': 'AA1112223',
            'jshshir': '11112222333344',
            'phone': '+998900000001',
        })
        self.assertEqual(response.status_code, 201, response.data)
        log = ActivityLog.objects.get()
        self.assertEqual(log.user, self.sales)
        self.assertEqual(log.entity, 'Client')
        self.assertEqual(log.action, ActivityLog.Action.CREATE)

    def test_logs_are_admin_only(self):
        self.client.force_authenticate(self.sales)
        self.assertEqual(self.client.get('/api/activity-logs/').status_code, 403)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get('/api/activity-logs/').status_code, 200)


class DeadlineNotificationTests(APITestCase):
    """check_deadlines: oxirgi kunlarda qizil eslatma yaratadi."""

    def setUp(self):
        ensure_default_categories()
        self.user = User.objects.create_user('admin', password='p', role=User.Role.ADMIN)
        self.client_obj = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )

    def test_command_creates_notifications(self):
        Contract.objects.create(
            client=self.client_obj, total_amount=Decimal('100000000'),
            status=Contract.Status.ACTIVE, term_days=90,
            start_date=localdate() - timedelta(days=85),
        )
        Loan.objects.create(
            lender_name='Bobur aka', amount=Decimal('5000000'),
            taken_at=localdate() - timedelta(days=25),
            deadline=localdate() + timedelta(days=5),
        )
        call_command('check_deadlines', stdout=StringIO())

        contract_note = Notification.objects.get(entity='Contract')
        self.assertEqual(contract_note.level, Notification.Level.DANGER)
        self.assertIn('5 kun', contract_note.title)
        self.assertTrue(Notification.objects.filter(entity='Loan').exists())

    def test_command_is_idempotent(self):
        Contract.objects.create(
            client=self.client_obj, total_amount=Decimal('100000000'),
            status=Contract.Status.ACTIVE, term_days=90,
            start_date=localdate() - timedelta(days=85),
        )
        call_command('check_deadlines', stdout=StringIO())
        call_command('check_deadlines', stdout=StringIO())
        self.assertEqual(Notification.objects.filter(entity='Contract').count(), 1)

    def test_notification_list_and_mark_read(self):
        Notification.objects.create(title='Test', level=Notification.Level.INFO)
        self.client.force_authenticate(self.user)
        response = self.client.get('/api/notifications/')
        self.assertEqual(response.status_code, 200)
        notification_id = response.data['results'][0]['id']
        response = self.client.post(f'/api/notifications/{notification_id}/mark-read/')
        self.assertTrue(response.data['is_read'])
