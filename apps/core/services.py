"""Menga taqalgan ish — navbat va yon panel hisoblagichi (EGALIK §2).

Bitta funksiya, ikkita endpoint: `GET /my-work/` (counts + items) va
`GET /sidebar-counts/` (faqat counts). Ikkalasi ham shu yerdagi bitta
ta'riflar to'plamidan chiqadi — raqamlar ta'rifan mos keladi, ikki joyda
ikki xil haqiqat bo'lmaydi.

Qoida: hisoblagich "mendan amal kutilmoqda" degani, "bu yerda N ta yozuv
bor" degani emas. Amal kutilmaydigan bo'lim umuman sanalmaydi.
"""

from datetime import timedelta

from django.db.models import DecimalField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils.timezone import localdate

from apps.core.utils import RED_ZONE_DAYS, sla_deadline, working_days_since

# Barcha bo'lim kalitlari — javobda doim to'liq to'plam (yo'g'i 0)
SECTIONS = (
    'contracts', 'leads', 'requests', 'configurations',
    'replenishments', 'low_stock', 'expense_requests', 'loans',
)

# TOPSHIRIQ #3: SLA qamrovi — tasdiq zanjiridagi hujjatlar. leads/loans o'z
# muddati bilan yuritiladi (check_deadlines), low_stock hujjat emas.
SLA_SECTIONS = {
    'contracts', 'requests', 'configurations', 'replenishments', 'expense_requests',
}


def _sla_settings():
    from apps.core.models import CompanyProfile

    profile = CompanyProfile.load()
    return profile.sla_cutoff_hour, profile.sla_working_days


def _stale_info(obj, cutoff_hour, working_days):
    """(muddati o'tganmi, necha ish kuni kutayotgani).

    Vaqt — `status_changed_at` (eski yozuvda `created_at`): hujjat AYNAN shu
    bosqichga qachon kelgani; `updated_at` yaroqsiz (izoh tahriri ham
    yangilaydi).
    """
    entered = obj.status_changed_at or obj.created_at
    deadline = sla_deadline(entered, cutoff_hour, working_days)
    today = localdate()
    if today <= deadline:
        return False, 0
    return True, working_days_since(localdate(entered), today)


def _contract_sources(user):
    from apps.sales.models import Contract

    qs = Contract.objects.select_related('client')
    if user.is_admin:
        reasons = {Contract.Status.PENDING_ADMIN: ('awaiting_admin_approve', 'warning')}
    elif user.is_bugalter:
        reasons = {
            Contract.Status.PENDING_BUGALTER: ('awaiting_didox', 'warning'),
            Contract.Status.APPROVED: ('awaiting_payment', 'warning'),
        }
    elif user.is_sales:
        qs = qs.filter(created_by=user)
        reasons = {
            Contract.Status.DRAFT: ('draft_to_submit', 'info'),
            Contract.Status.REJECTED: ('fix_and_resubmit', 'danger'),
            Contract.Status.APPROVED: ('awaiting_client_payment', 'warning'),
        }
    else:
        return None
    return {
        'section': 'contracts',
        'entity': 'Contract',
        'queryset': qs.filter(status__in=list(reasons)),
        'row': lambda obj: ('SHT', obj.number, reasons[obj.status], obj.total_amount, obj.currency),
    }


def _lead_source(user):
    from apps.sales.models import Lead

    if not user.is_sales:
        return None
    today = localdate()
    qs = (
        Lead.objects.select_related('client')
        .filter(created_by=user, next_contact_at__date__lte=today)
        .exclude(stage__in=[Lead.Stage.CONTRACT, Lead.Stage.LOST])
    )
    return {
        'section': 'leads',
        'entity': 'Lead',
        'queryset': qs,
        'row': lambda obj: (
            'Lead', obj.title,
            (
                'contact_due',
                'danger' if localdate(obj.next_contact_at) < today else 'warning',
            ),
            obj.expected_amount, 'UZS',
        ),
    }


def _request_source(user):
    from apps.configurator.models import ConfigurationRequest as Request

    if not user.is_engineer and not user.is_admin:
        return None
    if user.is_admin:
        return None  # zayavka navbati — engineer ishi
    qs = Request.objects.filter(
        Q(status=Request.Status.NEW) | Q(status=Request.Status.IN_PROGRESS, taken_by=user),
    )
    return {
        'section': 'requests',
        'entity': 'ConfigurationRequest',
        'queryset': qs,
        'row': lambda obj: (
            'ZVK', obj.number,
            ('take_request', 'warning') if obj.status == Request.Status.NEW
            else ('in_progress', 'info'),
            None, None,
        ),
    }


def _configuration_source(user):
    from apps.configurator.models import Configuration
    from apps.inventory.models import Stock

    if not user.is_engineer:
        return None
    zero = Value(0, output_field=DecimalField(max_digits=18, decimal_places=2))
    variant_stock = (
        Stock.objects.filter(product=OuterRef('variant'))
        .values('product').annotate(t=Sum('quantity')).values('t')
    )
    qs = (
        Configuration.objects.filter(created_by=user)
        .annotate(variant_stock=Coalesce(Subquery(variant_stock), zero))
        .filter(
            Q(status=Configuration.Status.DRAFT)
            # yig'ilmagan ready: variant hali omborga kirmagan (§10.1)
            | Q(status=Configuration.Status.READY, variant__isnull=False,
                variant_stock__lt=1)
        )
    )
    return {
        'section': 'configurations',
        'entity': 'Configuration',
        'queryset': qs,
        'row': lambda obj: (
            'CFG', obj.number,
            ('configure', 'info') if obj.status == Configuration.Status.DRAFT
            else ('assemble', 'warning'),
            None, None,
        ),
    }


def _replenishment_source(user):
    from apps.procurement.models import Replenishment

    qs = Replenishment.objects.all()
    if user.is_admin:
        reasons = {
            Replenishment.Status.PENDING_ADMIN: ('awaiting_admin_approve', 'warning'),
            Replenishment.Status.APPROVED: ('awaiting_payment', 'warning'),
        }
    elif user.is_bugalter:
        reasons = {
            Replenishment.Status.PENDING_BUGALTER: ('awaiting_check', 'warning'),
            Replenishment.Status.APPROVED: ('awaiting_payment', 'warning'),
        }
    elif user.is_sales:
        qs = qs.filter(Q(owner_sales=user) | Q(owner_sales__isnull=True))
        reasons = {Replenishment.Status.PENDING_SALES: ('client_approval', 'warning')}
    elif user.is_supplier:
        reasons = {
            Replenishment.Status.DRAFT: ('draft_to_submit', 'info'),
            Replenishment.Status.REJECTED: ('fix_and_resubmit', 'danger'),
            Replenishment.Status.ORDERED: ('track_delivery', 'info'),
            Replenishment.Status.IN_TRANSIT: ('track_delivery', 'info'),
            Replenishment.Status.CUSTOMS: ('track_delivery', 'info'),
        }
    else:
        return None
    return {
        'section': 'replenishments',
        'entity': 'Replenishment',
        'queryset': qs.filter(status__in=list(reasons)).prefetch_related('items'),
        'row': lambda obj: (
            'TLD', obj.number, reasons[obj.status], obj.total_amount, obj.currency,
        ),
    }


def _expense_source(user):
    from apps.finance.models import ExpenseRequest

    if not user.is_admin:
        return None
    qs = ExpenseRequest.objects.filter(status=ExpenseRequest.Status.PENDING)
    return {
        'section': 'expense_requests',
        'entity': 'ExpenseRequest',
        'queryset': qs,
        'row': lambda obj: (
            'Xarajat', obj.purpose[:60], ('decide_expense', 'warning'),
            obj.amount, obj.currency,
        ),
    }


def _loan_source(user):
    from apps.finance.models import Loan

    if not (user.is_admin or user.is_bugalter):
        return None
    today = localdate()
    # EGALIK §2.4: muddat sharti SQL da — Python property emas
    qs = Loan.objects.filter(
        status=Loan.Status.ACTIVE,
        deadline__lte=today + timedelta(days=RED_ZONE_DAYS),
    )
    return {
        'section': 'loans',
        'entity': 'Loan',
        'queryset': qs,
        'row': lambda obj: (
            'Qarz', obj.lender_name,
            ('loan_due', 'danger' if obj.deadline < today else 'warning'),
            obj.amount, obj.currency,
        ),
    }


def _low_stock_count(user):
    from apps.procurement.services import low_stock_queryset

    if not user.is_supplier and not user.is_admin:
        return 0
    if user.is_admin:
        return 0  # admin navbatida yetishmayotganlar yo'q (§2.3)
    return low_stock_queryset().count()


def _role_holder(role):
    """Hovuz uchun: roldagi (yagona) xodim — bugalter/admin bittadan (§3.0)."""
    from apps.accounts.models import User

    user = User.objects.filter(role=role, is_active=True).order_by('id').first()
    return user.display_name if user else None


def _admin_stale_items(cutoff_hour, working_days):
    """TOPSHIRIQ #3: boshqalarda muddatidan ortiq turgan ishlar — adminga.

    Qamrov jadvali (kim ushlab turibdi) — collect_work manbalarining o'zi,
    ikkinchi ta'rif emas: bu yerda faqat ADMIN bo'lmagan egalarning
    bosqichlari sanaladi (adminning o'z ishi o'z manbasida qizaradi).
    """
    from apps.accounts.models import User
    from apps.configurator.models import Configuration, ConfigurationRequest
    from apps.procurement.models import Replenishment
    from apps.sales.models import Contract

    bugalter_name = _role_holder(User.Role.BUGALTER)

    def contract_holder(obj):
        if obj.status in (Contract.Status.DRAFT, Contract.Status.REJECTED):
            return 'sales', obj.created_by.display_name if obj.created_by else None
        return 'bugalter', bugalter_name

    def replenishment_holder(obj):
        if obj.status in (Replenishment.Status.DRAFT, Replenishment.Status.REJECTED):
            return (
                'buyurtmachi',
                obj.created_by.display_name if obj.created_by else None,
            )
        if obj.status == Replenishment.Status.PENDING_SALES:
            return 'sales', obj.owner_sales.display_name if obj.owner_sales else None
        return 'bugalter', bugalter_name

    def request_holder(obj):
        if obj.taken_by:
            return 'engineer', obj.taken_by.display_name
        return 'engineer', None  # hovuz — hali hech kim olmagan

    def configuration_holder(obj):
        return 'engineer', obj.created_by.display_name if obj.created_by else None

    scopes = [
        (
            'contracts', 'Contract',
            Contract.objects.filter(status__in=[
                Contract.Status.DRAFT, Contract.Status.REJECTED,
                Contract.Status.PENDING_BUGALTER, Contract.Status.APPROVED,
            ]).select_related('created_by'),
            contract_holder,
            lambda obj: (obj.number, obj.total_amount, obj.currency),
        ),
        (
            'replenishments', 'Replenishment',
            Replenishment.objects.filter(status__in=[
                Replenishment.Status.DRAFT, Replenishment.Status.REJECTED,
                Replenishment.Status.PENDING_SALES,
                Replenishment.Status.PENDING_BUGALTER,
                Replenishment.Status.APPROVED,
            ]).select_related('created_by', 'owner_sales').prefetch_related('items'),
            replenishment_holder,
            lambda obj: (obj.number, obj.total_amount, obj.currency),
        ),
        (
            'requests', 'ConfigurationRequest',
            ConfigurationRequest.objects.filter(status__in=[
                ConfigurationRequest.Status.NEW,
                ConfigurationRequest.Status.IN_PROGRESS,
            ]).select_related('taken_by'),
            request_holder,
            lambda obj: (obj.number, None, None),
        ),
        (
            'configurations', 'Configuration',
            Configuration.objects.filter(
                status=Configuration.Status.DRAFT,
            ).select_related('created_by'),
            configuration_holder,
            lambda obj: (obj.number, None, None),
        ),
    ]

    stale_items = []
    for section, entity, queryset, holder, extras in scopes:
        for obj in queryset:
            stale, waiting = _stale_info(obj, cutoff_hour, working_days)
            if not stale:
                continue
            holder_role, holder_name = holder(obj)
            number, amount, currency = extras(obj)
            stale_items.append({
                'section': section,
                'entity': entity,
                'id': obj.pk,
                'number': number,
                'reason': 'stale',
                'amount': amount,
                'currency': currency,
                'level': 'danger',
                'holder_role': holder_role,
                'holder_name': holder_name,
                'waiting_days': waiting,
            })
    return stale_items


def collect_work(user, include_items=True):
    """Foydalanuvchiga taqalgan ishlar: {counts, items}.

    `include_items=False` (yon panel) — faqat COUNT so'rovlari yuradi,
    obyektlar yuklanmaydi (§2.4 unumdorlik talabi). TOPSHIRIQ #3: SLA
    qamrovidagi o'z qatori muddati o'tsa `danger` + `waiting_days` bo'ladi;
    adminga esa boshqalarda turib qolgan ishlar `reason='stale'` va
    `holder_role`/`holder_name` bilan qo'shiladi.
    """
    cutoff_hour, sla_days = _sla_settings()
    sources = [
        source
        for source in (
            _contract_sources(user),
            _lead_source(user),
            _request_source(user),
            _configuration_source(user),
            _replenishment_source(user),
            _expense_source(user),
            _loan_source(user),
        )
        if source is not None
    ]

    counts = {key: 0 for key in SECTIONS}
    items = []
    for source in sources:
        if include_items:
            rows = list(source['queryset'])
            counts[source['section']] += len(rows)
            for obj in rows:
                _, number, (reason, level), amount, currency = source['row'](obj)
                item = {
                    'section': source['section'],
                    'entity': source['entity'],
                    'id': obj.pk,
                    'number': number,
                    'reason': reason,
                    'amount': amount,
                    'currency': currency,
                    'level': level,
                }
                # Egasining o'zida ham qizarsin (#3) — adminga yetguncha ko'rsin
                if source['section'] in SLA_SECTIONS:
                    stale, waiting = _stale_info(obj, cutoff_hour, sla_days)
                    if stale:
                        item['level'] = 'danger'
                        item['waiting_days'] = waiting
                items.append(item)
        else:
            counts[source['section']] += source['queryset'].count()

    counts['low_stock'] = _low_stock_count(user)

    if user.is_admin:
        stale_items = _admin_stale_items(cutoff_hour, sla_days)
        for item in stale_items:
            counts[item['section']] += 1
        if include_items:
            items.extend(stale_items)

    if include_items:
        order = {'danger': 0, 'warning': 1, 'info': 2}
        items.sort(key=lambda row: order.get(row['level'], 3))
    return {'counts': counts, 'items': items if include_items else None}
