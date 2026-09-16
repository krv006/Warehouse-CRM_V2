from datetime import datetime, timedelta

from django.test import SimpleTestCase
from django.utils.timezone import get_current_timezone, localdate, make_aware, now

from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.clients.models import Client
from apps.core.utils import sla_deadline, working_days_since
from apps.sales.models import Contract


def aware(year, month, day, hour, minute=0):
    return make_aware(datetime(year, month, day, hour, minute), get_current_timezone())


class SlaDeadlineTests(SimpleTestCase):
    """TOPSHIRIQ #3 misollari aynan: kesim 16:00, 1 ish kuni."""

    def test_before_cutoff_same_day(self):
        # Du 12:00 -> muddat du oxiri (2026-09-14 — dushanba)
        self.assertEqual(
            sla_deadline(aware(2026, 9, 14, 12), 16, 1),
            datetime(2026, 9, 14).date(),
        )

    def test_after_cutoff_next_working_day(self):
        # Du 17:00 -> muddat se oxiri
        self.assertEqual(
            sla_deadline(aware(2026, 9, 14, 17), 16, 1),
            datetime(2026, 9, 15).date(),
        )

    def test_friday_evening_skips_weekend(self):
        # Ju 17:00 -> muddat du oxiri (2026-09-18 — juma)
        self.assertEqual(
            sla_deadline(aware(2026, 9, 18, 17), 16, 1),
            datetime(2026, 9, 21).date(),
        )

    def test_weekend_entry_starts_monday(self):
        # Shanba 10:00 -> muddat du oxiri (2026-09-19 — shanba)
        self.assertEqual(
            sla_deadline(aware(2026, 9, 19, 10), 16, 1),
            datetime(2026, 9, 21).date(),
        )

    def test_extra_working_days(self):
        # Du 12:00, 2 ish kuni -> se oxiri
        self.assertEqual(
            sla_deadline(aware(2026, 9, 14, 12), 16, 2),
            datetime(2026, 9, 15).date(),
        )

    def test_working_days_since_skips_weekend(self):
        # Ju -> se: du + se = 2 ish kuni
        self.assertEqual(
            working_days_since(
                datetime(2026, 9, 18).date(), datetime(2026, 9, 22).date(),
            ),
            2,
        )


class StatusChangedAtTests(APITestCase):
    """status_changed_at faqat holat o'zgarganda yoziladi — updated_at emas."""

    def setUp(self):
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )

    def test_set_on_create_and_only_on_status_change(self):
        contract = Contract.objects.create(client=self.mijoz, created_by=self.sales)
        self.assertIsNotNone(contract.status_changed_at)
        first = contract.status_changed_at

        # Izoh tahriri holat vaqtini o'zgartirmaydi
        contract = Contract.objects.get(pk=contract.pk)
        contract.note = 'izoh'
        contract.save()
        self.assertEqual(contract.status_changed_at, first)

        # Holat o'zgarishi yangilaydi
        contract = Contract.objects.get(pk=contract.pk)
        contract.status = Contract.Status.PENDING_BUGALTER
        contract.save()
        self.assertGreater(contract.status_changed_at, first)


class StaleWorkTests(APITestCase):
    """Bir ish kunidan ortiq turgan ish: egasida ham, adminda ham qizil."""

    def setUp(self):
        self.admin = User.objects.create_user('adm', password='p', role=User.Role.ADMIN)
        self.bugalter = User.objects.create_user(
            'bug', password='p', role=User.Role.BUGALTER,
            first_name='Aziz', last_name='Sobirov',
        )
        self.sales = User.objects.create_user('sal', password='p', role=User.Role.SALES)
        self.mijoz = Client.objects.create(
            type=Client.Type.INDIVIDUAL, full_name='Ali Valiyev',
            passport='AA1112223', jshshir='11112222333344', phone='+998900000001',
        )
        self.contract = Contract.objects.create(
            client=self.mijoz, created_by=self.sales,
            status=Contract.Status.PENDING_BUGALTER,
        )

    def _make_stale(self):
        # 6 kun oldin, ertalab kelgan — har qanday hafta kunida muddati o'tgan
        Contract.objects.filter(pk=self.contract.pk).update(
            status_changed_at=now() - timedelta(days=6),
        )

    def _work(self, user):
        self.client.force_authenticate(user)
        return self.client.get('/api/my-work/').data

    def test_fresh_work_is_not_stale(self):
        work = self._work(self.bugalter)
        row = next(r for r in work['items'] if r['entity'] == 'Contract')
        self.assertNotEqual(row['level'], 'danger')
        self.assertNotIn('waiting_days', row)

    def test_holder_sees_own_work_red(self):
        """Egasining o'zida ham qizarsin — adminga yetguncha o'zi ko'radi."""
        self._make_stale()
        work = self._work(self.bugalter)
        row = next(r for r in work['items'] if r['entity'] == 'Contract')
        self.assertEqual(row['level'], 'danger')
        self.assertGreaterEqual(row['waiting_days'], 1)

    def test_admin_sees_stale_work_with_holder(self):
        self._make_stale()
        work = self._work(self.admin)
        row = next(r for r in work['items'] if r['reason'] == 'stale')
        self.assertEqual(row['entity'], 'Contract')
        self.assertEqual(row['level'], 'danger')
        self.assertEqual(row['holder_role'], 'bugalter')
        self.assertEqual(row['holder_name'], 'Aziz Sobirov')
        self.assertGreaterEqual(row['waiting_days'], 1)
        # counts bilan items mos (sidebar ham xuddi shu funksiya)
        self.assertEqual(work['counts']['contracts'], 1)
        self.client.force_authenticate(self.admin)
        sidebar = self.client.get('/api/sidebar-counts/').data
        self.assertEqual(sidebar, work['counts'])

    def test_admin_does_not_see_fresh_work_of_others(self):
        work = self._work(self.admin)
        self.assertFalse([r for r in work['items'] if r['reason'] == 'stale'])
        self.assertEqual(work['counts']['contracts'], 0)

    def test_stale_replenishment_shows_owner_sales_holder(self):
        from apps.inventory.services import main_warehouse
        from apps.procurement.models import Replenishment

        replenishment = Replenishment.objects.create(
            warehouse=main_warehouse(), status=Replenishment.Status.PENDING_SALES,
            owner_sales=self.sales,
        )
        Replenishment.objects.filter(pk=replenishment.pk).update(
            status_changed_at=now() - timedelta(days=6),
        )
        work = self._work(self.admin)
        row = next(
            r for r in work['items']
            if r['reason'] == 'stale' and r['entity'] == 'Replenishment'
        )
        self.assertEqual(row['holder_role'], 'sales')
        self.assertEqual(row['holder_name'], 'sal')
