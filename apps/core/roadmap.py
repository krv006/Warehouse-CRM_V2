"""Zanjir roadmapi (YANGI-OQIM B8) — jarayonning ko'zgusi.

Bitta zayavka ochilgandan yakungacha 18 qadam: nima bajarildi, hozir kimda,
oldinda nima bor. Uch kirish nuqtasi (ZVK/CFG/SHT) bir xil javob qaytaradi.

Ko'rinish qoidasi hujjatlarnikiga BO'YSUNMAYDI: zanjirdagi beshta rol ham
to'liq ko'radi. Evaziga **pulga oid hech narsa qaytarilmaydi** — summa,
narx, qoldiq yo'q. Bu chegara qat'iy: money maydoni qo'shilsa ruxsat
modeli buziladi.

Front hech narsani qayta hisoblamaydi: `label`, `state`, `tone`,
`waiting_days`, `deadline`, `can_open`, `repeats`, `current_key` — tayyor.
SLA — mavjud `sla_deadline`/`working_days_since` dan (yangi hisob yo'q).
"""

from django.utils.timezone import localdate

from apps.core.utils import sla_deadline, working_days_since

# Qadam kalitlari va nomlari — §2 jadvali (18 qadam, ro'yxat qisqarmaydi)
STEPS = [
    ('zvk_created', 'Zayavka yozildi', 'sales'),
    ('taken', 'Engineer oldi', 'engineer'),
    ('price_request', "Narx so'rovi", 'buyurtmachi'),
    ('submitted', "Ko'rikka yuborildi", 'engineer'),
    ('sales_review', "Sales ko'rigi", 'sales'),
    ('contract_created', 'Shartnoma ochildi', 'sales'),
    ('contract_submitted', 'Bugalterga yuborildi', 'sales'),
    ('didox_sent', 'Didoxga yuborildi', 'bugalter'),
    ('didox_confirmed', 'Didox tasdiqlandi', 'bugalter'),
    ('admin_approve', "Admin tasdig'i", 'admin'),
    ('approved_waiting', 'Tasdiqlandi, pul kutilmoqda', 'bugalter'),
    ('prepayment', "Boshlang'ich to'lov", 'bugalter'),
    ('procurement_sent', 'Buyurtmachiga yuborildi', 'engineer'),
    ('procurement_chain', "TLD zanjiri (kirimgacha)", 'buyurtmachi'),
    ('assemble', "Yig'ish", 'engineer'),
    ('finalize', 'ACT bilan yakunlash', 'engineer'),
    ('ship', 'Yetkazish', 'buyurtmachi'),
    ('completed', 'Yakunlandi', 'sales'),
]

ROLE_LABELS = {
    'admin': 'Admin',
    'bugalter': 'Bugalter',
    'sales': 'Sales',
    'engineer': 'Engineer',
    'buyurtmachi': 'Buyurtmachi',
}

# 13–16 qadamlar to'lovgacha qulflangan (B4)
PAYMENT_GATED = {'procurement_sent', 'procurement_chain', 'assemble', 'finalize'}


def resolve_chain(document):
    """Kirish nuqtasidan butun zanjirni yig'adi: (ZVK, CFG, SHT)."""
    from apps.configurator.models import Configuration, ConfigurationRequest
    from apps.sales.models import Contract

    request_obj = configuration = contract = None
    if isinstance(document, Contract):
        contract = document
        configuration = document.configuration
    elif isinstance(document, Configuration):
        configuration = document
    elif isinstance(document, ConfigurationRequest):
        request_obj = document
        configuration = document.configuration
    if configuration is not None and request_obj is None:
        request_obj = configuration.requests.order_by('-created_at').first()
    if request_obj is not None and configuration is None:
        configuration = request_obj.configuration
    if configuration is not None and contract is None:
        contract = (
            configuration.contracts
            .exclude(status=Contract.Status.CANCELLED)
            .order_by('-id')
            .first()
        ) or configuration.contracts.order_by('-id').first()
    return request_obj, configuration, contract


def _actor(user_obj, role):
    return {
        'id': user_obj.pk if user_obj else None,
        'full_name': user_obj.display_name if user_obj else None,
        'role': role,
        'role_label': ROLE_LABELS.get(role, role),
    }


def _document(kind, obj):
    if obj is None:
        return None
    return {'type': kind, 'id': obj.pk, 'number': obj.number}


def _can_open(user, kind, obj, contract=None):
    """§3.13 matritsasi — qaysi qadam ichiga kirish mumkinligini backend aytadi."""
    if obj is None:
        return False
    if user.is_admin:
        return True
    if user.is_sales:
        if kind == 'request':
            return obj.created_by_id == user.id
        if kind == 'configuration':
            return obj.requests.filter(created_by=user).exists()
        if kind == 'contract':
            return obj.created_by_id == user.id
        return False
    if user.is_engineer:
        if kind == 'configuration':
            return True
        if kind == 'request':
            return obj.taken_by_id == user.id or obj.status == obj.Status.NEW
        return False
    if user.is_bugalter:
        return kind in ('contract', 'replenishment')
    if user.is_supplier:
        if kind == 'replenishment':
            return True
        if kind == 'contract':
            return obj.status == 'active' and obj.delivered_at is None
        return False
    return False


def build_roadmap(document, user):
    """Bitta to'liq javob — front saralamaydi, qayta hisoblamaydi (B8)."""
    from apps.configurator.models import (
        Configuration,
        ConfigurationApproval,
        ConfigurationRequestEvent,
    )
    from apps.core.models import CompanyProfile
    from apps.procurement.models import Replenishment
    from apps.sales.models import Contract, ContractApproval

    request_obj, configuration, contract = resolve_chain(document)

    events = list(request_obj.events.select_related('created_by')) if request_obj else []
    approvals = list(
        configuration.approvals.select_related('decided_by')
    ) if configuration else []
    c_approvals = list(
        contract.approvals.select_related('decided_by')
    ) if contract else []
    replenishment = None
    if configuration is not None:
        replenishment = (
            configuration.replenishments
            .exclude(status=Replenishment.Status.CANCELLED)
            .order_by('-id')
            .first()
        )

    def ev(stage):
        return [e for e in events if e.stage == stage]

    def appr(step, decision=None, human_only=False):
        rows = [a for a in c_approvals if a.step == step]
        if decision:
            rows = [a for a in rows if a.decision == decision]
        if human_only:
            rows = [a for a in rows if a.decided_by_id]
        return rows

    paid = bool(contract and contract.status in ('active', 'completed'))
    cancelled_chain = bool(
        (request_obj and request_obj.status == 'cancelled')
        or (configuration and configuration.status == 'cancelled')
        or (contract and contract.status == 'cancelled')
    )

    # ---- har bir qadam: (done, at, actor_user, actor_role, document, repeats, skipped)
    engineer = configuration.created_by if configuration else (
        request_obj.taken_by if request_obj else None
    )
    sales_owner = request_obj.created_by if request_obj else (
        contract.created_by if contract else None
    )

    price_asked = ev(ConfigurationRequestEvent.Stage.PRICE_ASKED)
    price_given = ev(ConfigurationRequestEvent.Stage.PRICE_GIVEN)
    returned = ev(ConfigurationRequestEvent.Stage.RETURNED)

    cfg_approved_rows = [
        a for a in approvals
        if a.decision == ConfigurationApproval.Decision.APPROVED
    ]
    cfg_rejected_rows = [
        a for a in approvals
        if a.decision == ConfigurationApproval.Decision.REJECTED
    ]

    didox_rows = appr(ContractApproval.Step.DIDOX)
    admin_rows = appr(ContractApproval.Step.ADMIN, human_only=True)
    admin_auto = appr(ContractApproval.Step.ADMIN)
    payment_rows = appr(ContractApproval.Step.PAYMENT)
    first_payment = (
        contract.payments.order_by('paid_at').first() if contract else None
    )

    cfg_done_states = {'approved', 'ready', 'sold'}
    delivered = bool(contract and contract.delivered_at)
    tld_needed = replenishment is not None

    data = {}
    data['zvk_created'] = dict(
        done=request_obj is not None,
        at=request_obj.created_at if request_obj else None,
        who=request_obj.created_by if request_obj else None,
        doc=('request', request_obj),
        repeats=len(ev(ConfigurationRequestEvent.Stage.RESENT)),
    )
    data['taken'] = dict(
        done=configuration is not None,
        at=configuration.created_at if configuration else None,
        who=engineer,
        doc=('configuration', configuration),
        repeats=len(returned),
    )
    price_done = bool(price_given) or (
        configuration is not None
        and configuration.status in {'pending_sales'} | cfg_done_states
    )
    data['price_request'] = dict(
        done=bool(price_given),
        at=price_given[-1].created_at if price_given else None,
        who=price_given[-1].created_by if price_given else None,
        doc=('configuration', configuration),
        repeats=max(len(price_asked) - 1, 0),
        skipped=not price_asked and price_done,
        current_override=bool(price_asked and not price_given),
    )
    submitted_done = configuration is not None and (
        configuration.status in {'pending_sales'} | cfg_done_states
    )
    data['submitted'] = dict(
        done=submitted_done,
        at=configuration.status_changed_at
        if configuration and configuration.status == 'pending_sales' else None,
        who=engineer,
        doc=('configuration', configuration),
    )
    review_done = configuration is not None and configuration.status in cfg_done_states
    data['sales_review'] = dict(
        done=review_done,
        at=cfg_approved_rows[-1].created_at if cfg_approved_rows else None,
        who=cfg_approved_rows[-1].decided_by if cfg_approved_rows else sales_owner,
        doc=('configuration', configuration),
        repeats=len(cfg_rejected_rows),
    )
    data['contract_created'] = dict(
        done=contract is not None,
        at=contract.created_at if contract else None,
        who=contract.created_by if contract else None,
        doc=('contract', contract),
    )
    submitted_contract = bool(
        contract and contract.status not in ('draft', 'rejected', 'cancelled')
    )
    data['contract_submitted'] = dict(
        done=submitted_contract,
        at=None,
        who=contract.created_by if contract else None,
        doc=('contract', contract),
    )
    data['didox_sent'] = dict(
        done=bool(contract and contract.didox_sent_at),
        at=contract.didox_sent_at if contract else None,
        who=didox_rows[0].decided_by if didox_rows else None,
        doc=('contract', contract),
        # B11 mosligi: eski bitta qadamli approve — didox_sent_at bo'sh,
        # lekin zanjir o'tib ketgan bo'lsa skipped
        skipped=bool(
            contract and not contract.didox_sent_at
            and contract.status in ('pending_admin', 'approved', 'active', 'completed')
        ),
    )
    data['didox_confirmed'] = dict(
        done=bool(contract and contract.didox_accepted_at),
        at=contract.didox_accepted_at if contract else None,
        who=didox_rows[-1].decided_by if didox_rows else None,
        doc=('contract', contract),
        skipped=bool(
            contract and not contract.didox_accepted_at
            and contract.status in ('pending_admin', 'approved', 'active', 'completed')
        ),
    )
    admin_done = bool(
        contract and contract.status in ('approved', 'active', 'completed')
    )
    admin_skipped = bool(
        admin_done and not admin_rows
        and any(a.decided_by_id is None for a in admin_auto)
    )
    data['admin_approve'] = dict(
        done=admin_done and not admin_skipped,
        at=admin_rows[-1].created_at if admin_rows else None,
        who=admin_rows[-1].decided_by if admin_rows else None,
        doc=('contract', contract),
        skipped=admin_skipped,
    )
    data['approved_waiting'] = dict(
        done=bool(
            contract and contract.status in ('approved', 'active', 'completed')
        ),
        at=None,
        who=None,
        doc=('contract', contract),
    )
    data['prepayment'] = dict(
        done=paid,
        at=first_payment.paid_at if first_payment else None,
        who=payment_rows[0].decided_by if payment_rows else None,
        doc=('contract', contract),
    )
    assembled = bool(configuration and configuration.assembled_at)
    data['procurement_sent'] = dict(
        done=tld_needed,
        at=replenishment.created_at if replenishment else None,
        who=replenishment.created_by if replenishment else None,
        doc=('replenishment', replenishment),
        skipped=not tld_needed and assembled,  # hammasi omborda bor edi
    )
    tld_delivered = bool(
        replenishment and replenishment.status == Replenishment.Status.DELIVERED
    )
    data['procurement_chain'] = dict(
        done=tld_delivered,
        at=replenishment.delivered_at if tld_delivered else None,
        who=None,
        doc=('replenishment', replenishment),
        skipped=not tld_needed and assembled,
    )
    data['assemble'] = dict(
        done=assembled,
        at=configuration.assembled_at if configuration else None,
        who=engineer,
        doc=('configuration', configuration),
    )
    finalized = bool(configuration and configuration.status in ('ready', 'sold'))
    data['finalize'] = dict(
        done=finalized,
        at=None,
        who=engineer,
        doc=('configuration', configuration),
    )
    data['ship'] = dict(
        done=delivered,
        at=contract.delivered_at if contract else None,
        who=None,
        doc=('contract', contract),
    )
    completed = bool(contract and contract.status == 'completed')
    data['completed'] = dict(
        done=completed,
        at=contract.status_changed_at if completed and contract else None,
        who=None,
        doc=('contract', contract),
    )

    # ---- joriy qadam va holatlar
    current_key = None
    for key, _, _ in STEPS:
        row = data[key]
        if row.get('skipped'):
            continue
        if row.get('current_override'):
            current_key = key
            break
        if not row['done']:
            current_key = key
            break

    profile = CompanyProfile.load()
    cutoff, days = profile.sla_cutoff_hour, profile.sla_working_days

    # SLA manbai — joriy bosqich qaysi hujjatda turgan bo'lsa o'sha
    def sla_for(doc_pair):
        kind, obj = doc_pair
        source = obj if obj is not None else (contract or configuration or request_obj)
        entered = getattr(source, 'status_changed_at', None) if source else None
        if entered is None:
            return 'warning', None, None
        deadline = sla_deadline(entered, cutoff, days)
        today = localdate()
        if today > deadline:
            return 'danger', working_days_since(localdate(entered), today), deadline
        return 'warning', 0, deadline

    steps = []
    for key, label, default_role in STEPS:
        row = data[key]
        doc_kind, doc_obj = row.get('doc') or (None, None)
        waiting_days = deadline = None
        if row.get('skipped'):
            state, tone = 'skipped', 'muted'
        elif row['done'] and key != current_key:
            state, tone = 'done', 'success'
        elif key == current_key:
            if cancelled_chain:
                state, tone = 'cancelled', 'cancelled'
            else:
                state = 'current'
                tone, waiting_days, deadline = sla_for((doc_kind, doc_obj))
        else:
            # navbat kelmagan; 13–16 to'lovgacha qulf (B4) — blocked
            if key in PAYMENT_GATED and not paid and not row['done']:
                state, tone = 'blocked', 'muted'
            else:
                state, tone = 'pending', 'muted'

        actor_user = row.get('who')
        if state in ('pending', 'blocked'):
            actor_user = None  # kelajak qadamda ism yo'q — faqat rol
        steps.append({
            'key': key,
            'label': label,
            'state': state,
            'tone': tone,
            'actor': _actor(actor_user, default_role),
            'at': row.get('at'),
            'waiting_days': waiting_days if tone == 'danger' else None,
            'deadline': deadline,
            'document': _document(doc_kind, doc_obj),
            'can_open': _can_open(user, doc_kind, doc_obj, contract),
            'repeats': row.get('repeats', 0),
        })

    client = None
    if configuration is not None and configuration.client_id:
        client = configuration.client
    elif request_obj is not None and request_obj.client_id:
        client = request_obj.client
    elif contract is not None:
        client = contract.client

    return {
        'request': (
            {
                'id': request_obj.pk,
                'number': request_obj.number,
                'status': request_obj.status,
            } if request_obj else None
        ),
        'client_name': client.display_name if client else None,
        'current_key': current_key,
        'steps': steps,
    }
