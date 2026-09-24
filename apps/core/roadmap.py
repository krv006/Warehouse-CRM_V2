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

from datetime import datetime, time

from django.utils.timezone import localdate, make_aware

from apps.core.utils import sla_deadline, working_days_since


def _deal_step(models, done_pred):
    """14-§8: qadamni savdo darajasida yig'adi — ENG ORQADA qolgan model
    bo'yicha (savdo "bajarildi" emas, toki HAMMA model bajarilmaguncha).

    Qaytaradi: `(hammasi_tugadimi, orqada_qolgan_konfiguratsiya, models_bloki)`.
    Hammasi tugagan bo'lsa "orqada qolgan" — ro'yxatdagi oxirgi model
    (ko'rsatish uchun neytral tanlov).
    """
    pending = [cfg for cfg in models if not done_pred(cfg)]
    lagging = pending[0] if pending else models[-1]
    return (
        not pending,
        lagging,
        {
            'done': len(models) - len(pending),
            'total': len(models),
            'pending': [{'id': cfg.id, 'number': cfg.number} for cfg in pending],
        },
    )


def _as_datetime(value):
    """QOLGAN-ISHLAR #3: `since` manbalari aralash — ba'zilari DateField
    (masalan `Replenishment.delivered_at`), `sla_deadline` esa datetime
    kutadi. `datetime`ning o'zi `hour`ga ega, oddiy `date` esa yo'q.
    """
    if value is None or hasattr(value, 'hour'):
        return value
    return make_aware(datetime.combine(value, time.min))

# Qadam kalitlari va nomlari — §2 jadvali, 20-§3.5 dan keyin 20 qadam
STEPS = [
    ('zvk_created', 'Zayavka yozildi', 'sales'),
    ('taken', 'Engineer oldi', 'engineer'),
    ('price_request', "Narx so'rovi", 'buyurtmachi'),
    ('submitted', "Ko'rikka yuborildi", 'engineer'),
    ('sales_review', "Sales ko'rigi", 'sales'),
    ('contract_created', 'Shartnoma ochildi', 'sales'),
    ('contract_submitted', 'Bugalterga yuborildi', 'sales'),
    # 12-§1: sales -> bugalter -> admin -> Didox -> to'lov. Admin ruxsati
    # endi ishdan (Didoxdan) OLDIN so'raladi, hujjat hali kuchga kirmagan
    ('bugalter_check', 'Bugalter tekshiruvi', 'bugalter'),
    ('admin_approve', "Admin tasdig'i", 'admin'),
    ('didox_sent', 'Didoxga yuborildi', 'bugalter'),
    ('didox_confirmed', 'Didox tasdiqlandi', 'bugalter'),
    ('approved_waiting', 'Tasdiqlandi, pul kutilmoqda', 'bugalter'),
    ('prepayment', "Boshlang'ich to'lov", 'bugalter'),
    ('procurement_sent', 'Buyurtmachiga yuborildi', 'engineer'),
    ('procurement_chain', "TLD zanjiri (kirimgacha)", 'buyurtmachi'),
    ('assemble', "Yig'ish", 'engineer'),
    ('finalize', 'ACT bilan yakunlash', 'engineer'),
    # 20-§3.5: ACT — tarkib o'zgarishining moliyaviy asosi, bugalter
    # tasdig'idan o'tmaguncha mol chiqmasin (`ship` qulflangan)
    ('act_review', "ACT tasdig'i", 'bugalter'),
    ('ship', 'Yetkazish', 'sales'),
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

# 6-to'plam §1–2: SHARTLI qadamlar — zanjirda bor-yo'qligi ish borishiga
# bog'liq. Ular `current` ni "birinchi bajarilmagan" qoidasi orqali OLMAYDI:
# joriy bo'lishining yagona yo'li — haqiqatan boshlangan bo'lsa
# (`current_override`: narx so'ralgan, TLD ochilgan). Shart aniq
# bo'lmaydigan holatda `skipped` — front chizmaydi.
OPTIONAL = {
    'price_request', 'admin_approve', 'procurement_sent', 'procurement_chain',
}


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
        if request_obj is None:
            # 12-§2 (B): qo'shimcha model qatori — zayavkaga faqat
            # ConfigurationRequestLine orqali ulangan (asosiy FK bo'sh)
            extra_line = configuration.extra_request_lines.select_related('request').first()
            request_obj = extra_line.request if extra_line else None
    if request_obj is not None and configuration is None:
        configuration = request_obj.configuration
    if configuration is not None and contract is None:
        # 12-§2 (C): ikkinchi (yoki keyingi) model faqat qator orqali
        # ulangan bo'lishi mumkin — `active_contract` buni ham topadi
        contract = (
            configuration.active_contract
            or configuration.contracts.order_by('-id').first()
        )
    return request_obj, configuration, contract


def chain_is_closed(request_obj, configuration, contract):
    """Zanjir yopiqmi — bosh sahifada yopilgani kerak emas (7-to'plam §1)."""
    if contract is not None:
        return contract.status in ('completed', 'cancelled')
    if configuration is not None:
        return configuration.status == 'cancelled'
    if request_obj is not None:
        return request_obj.status in ('cancelled', 'archived')
    return True


def _replenishment_actor_ids(replenishment):
    ids = {replenishment.created_by_id, replenishment.owner_sales_id}
    ids |= set(replenishment.approvals.values_list('decided_by_id', flat=True))
    ids |= set(replenishment.events.values_list('created_by_id', flat=True))
    return ids


def chain_actor_ids(request_obj, configuration, contract):
    """Zanjirga QO'L TEKKIZGAN har bir odam (10-to'plam §5).

    Hammasi mavjud maydonlardan yig'iladi — yangi model yo'q: egalari,
    tarix yozuvlari (eventlar), tasdiqlar, to'lovlar, TLD bosqichlari.
    Avtomatik yozuvlardagi `None` tashlanadi.
    """
    ids = set()
    if request_obj is not None:
        ids |= {request_obj.created_by_id, request_obj.taken_by_id}
        ids |= set(request_obj.events.values_list('created_by_id', flat=True))
    if configuration is not None:
        ids.add(configuration.created_by_id)
        ids |= set(configuration.approvals.values_list('decided_by_id', flat=True))
        for replenishment in configuration.replenishments.all():
            ids |= _replenishment_actor_ids(replenishment)
    if contract is not None:
        ids |= {contract.created_by_id, getattr(contract, 'delivered_by_id', None)}
        ids |= set(contract.approvals.values_list('decided_by_id', flat=True))
        ids |= set(contract.payments.values_list('created_by_id', flat=True))
        for replenishment in contract.replenishments.all():
            ids |= _replenishment_actor_ids(replenishment)
    ids.discard(None)
    return ids


def _participates(user, request_obj, configuration, contract, current_role):
    """Qatnashish ta'rifi (10-to'plam §5): tarix + hovuz.

    Zanjir unga QO'L TEKKIZGAN har bir odamda ko'rinadi — o'sha paytdan
    boshlab, ish yopilguncha (navbat o'tib ketsa ham). Hali hech kim
    tegmagan bosqichda esa u navbatdagi rolning HOVUZIDA turadi: joriy
    rol mos kelsa-yu, o'sha roldan allaqachon kimdir ishlagan bo'lsa —
    ko'rinmaydi (yangi zayavkani hamma engineer ko'radi, olingandan
    keyin faqat oluvchisi — shu qoidadan o'z-o'zidan kelib chiqadi).
    Admin hammasini ko'radi.
    """
    if user.is_admin:
        return True
    actors = chain_actor_ids(request_obj, configuration, contract)
    if user.id in actors:
        return True
    role_flags = {
        'admin': user.is_admin,
        'sales': user.is_sales,
        'engineer': user.is_engineer,
        'bugalter': user.is_bugalter,
        'buyurtmachi': user.is_supplier,
    }
    if not (current_role and role_flags.get(current_role)):
        return False
    # Hovuz: joriy roldan hali HECH KIM ishlamagan bo'lsagina
    from apps.accounts.models import User

    actor_roles = set(
        User.objects.filter(pk__in=actors).values_list('role', flat=True)
    )
    return current_role not in actor_roles


def build_roadmap_list(user, state='open'):
    """Foydalanuvchi qatnashayotgan zanjirlar ro'yxati (7-to'plam §1).

    Har bir element — detal `roadmap` javobining AYNAN o'sha shakli, front
    bitta komponentni o'zgarishsiz ishlatadi. Tartib: (1) joriy qadami
    muddatdan o'tgan, (2) joriy qadami shu foydalanuvchida, (3) kutish
    vaqti bo'yicha kamayish.
    """
    from apps.configurator.models import Configuration, ConfigurationRequest
    from apps.sales.models import Contract

    # Har bir zanjir bitta ildizdan olinadi: ZVK; ZVK'siz CFG; yolg'iz SHT.
    # 10-§5 (tezlik): ishtirokchi yig'ish qo'shimcha so'rov qilmasin deb
    # kerakli bog'lanishlar prefetch bilan birga keladi
    roots = list(
        ConfigurationRequest.objects
        .select_related('client', 'configuration', 'created_by', 'taken_by')
        .prefetch_related(
            'events',
            'configuration__approvals',
            'configuration__replenishments__approvals',
            'configuration__replenishments__events',
            'configuration__contracts__approvals',
            'configuration__contracts__payments',
        )
        .order_by('-id')
    )
    roots += list(
        Configuration.objects
        .filter(requests__isnull=True)
        .select_related('client', 'created_by')
        .prefetch_related(
            'approvals', 'replenishments__approvals', 'replenishments__events',
            'contracts__approvals', 'contracts__payments',
        )
        .order_by('-id')
    )
    roots += list(
        Contract.objects
        .filter(configuration__isnull=True)
        .select_related('client', 'created_by')
        .prefetch_related(
            'approvals', 'payments',
            'replenishments__approvals', 'replenishments__events',
        )
        .order_by('-id')
    )

    role_flags = {
        'admin': user.is_admin,
        'sales': user.is_sales,
        'engineer': user.is_engineer,
        'bugalter': user.is_bugalter,
        'buyurtmachi': user.is_supplier,
    }

    rows, seen = [], set()
    for root in roots:
        request_obj, configuration, contract = resolve_chain(root)
        key = (
            ('zvk', request_obj.pk) if request_obj
            else ('cfg', configuration.pk) if configuration
            else ('sht', contract.pk)
        )
        if key in seen:
            continue
        seen.add(key)

        closed = chain_is_closed(request_obj, configuration, contract)
        if state == 'open' and closed:
            continue
        if state == 'closed' and not closed:
            continue

        roadmap = build_roadmap(root, user)
        current = next(
            (s for s in roadmap['steps'] if s['key'] == roadmap['current_key']),
            None,
        )
        current_role = current['actor']['role'] if current else None
        if not _participates(user, request_obj, configuration, contract, current_role):
            continue

        overdue = bool(current and current['tone'] == 'danger')
        mine = bool(current_role and role_flags.get(current_role))
        waiting = (current or {}).get('waiting_days') or 0
        rows.append(((not overdue, not mine, -waiting), roadmap))

    rows.sort(key=lambda pair: pair[0])
    return [roadmap for _, roadmap in rows]


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
            # 12-§2 (B): qo'shimcha model qatori — zayavka qator orqali ulangan
            return (
                obj.requests.filter(created_by=user).exists()
                or obj.extra_request_lines.filter(request__created_by=user).exists()
            )
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
    released = ev(ConfigurationRequestEvent.Stage.RELEASED)

    cfg_approved_rows = [
        a for a in approvals
        if a.decision == ConfigurationApproval.Decision.APPROVED
    ]
    cfg_rejected_rows = [
        a for a in approvals
        if a.decision == ConfigurationApproval.Decision.REJECTED
    ]

    # 12-§6: "bajarilgan" faqat JORIY aylanishga tegishli bo'lsin — rad
    # etilgandan keyingi qadamlar eski (rad etilmagan) qatorlardan olinadi
    bugalter_rows = appr(
        ContractApproval.Step.BUGALTER, decision=ContractApproval.Decision.APPROVED,
    )
    didox_rows = appr(ContractApproval.Step.DIDOX)
    admin_rows = appr(
        ContractApproval.Step.ADMIN, decision=ContractApproval.Decision.APPROVED,
        human_only=True,
    )
    admin_auto = appr(
        ContractApproval.Step.ADMIN, decision=ContractApproval.Decision.APPROVED,
    )
    payment_rows = appr(ContractApproval.Step.PAYMENT)
    first_payment = (
        contract.payments.order_by('paid_at').first() if contract else None
    )
    # 20-§2.1: bu son `contract_submitted` ("Bugalterga yuborildi")
    # qadamida "N marta qaytarildi" bo'lib chiqadi — ya'ni SALES necha
    # marta qayta yuborgani. Admin→bugalter qaytarishi (`returned_to=
    # 'bugalter'`) boshqa qadamga tegishli — bu yerga qo'shilmasin, aks
    # holda chiziq bo'lmagan narsani aytardi (eski yozuvlarda `''` —
    # baribir sanaladi, moslik buzilmaydi).
    contract_rejections = len([
        a for a in c_approvals
        if a.decision == ContractApproval.Decision.REJECTED and a.returned_to != 'bugalter'
    ])
    bugalter_returns = len([
        a for a in c_approvals
        if a.decision == ContractApproval.Decision.REJECTED and a.returned_to == 'bugalter'
    ])
    # Rad etilgandan keyingi timestamp maydonlari (didox_sent_at/
    # didox_accepted_at) eski qiymatini saqlab qoladi — "bajarilgan"
    # belgisi shu tufayli joriy aylanishga tegishli bo'lishi shart
    last_reject_at = max(
        (a.created_at for a in c_approvals if a.decision == ContractApproval.Decision.REJECTED),
        default=None,
    )

    def after_last_reject(moment):
        return bool(moment) and (last_reject_at is None or moment > last_reject_at)

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
    # 12-§3: engineer ishga olishdan OLDIN rad etsa (`returned`) ish endi
    # sales'da — konfiguratsiya yo'q, lekin "engineer kutilmoqda" degan
    # noto'g'ri taassurot bermasin (`release`dan farqli: u hovuzga qaytaradi)
    returned_now = bool(
        request_obj and request_obj.status == 'returned'
    )
    data['taken'] = dict(
        done=configuration is not None,
        at=configuration.created_at if configuration else None,
        who=sales_owner if returned_now else engineer,
        role='sales' if returned_now else None,
        label='Sales tuzatmoqda' if returned_now else None,
        # QOLGAN-ISHLAR #6: joriy bo'lganda hujjat har doim bo'lishi kerak —
        # konfiguratsiya hali yo'q bo'lsa (new yoki returned), ish zayavka
        # sahifasida bajariladi ("Ishga olish" o'sha yerda bosiladi)
        doc=('configuration', configuration) if configuration else ('request', request_obj),
        # 9-to'plam §2: "ishga olish" necha marta qaytadan boshlangani —
        # rad etilganlar (returned) + hovuzga qaytarilganlar (released)
        repeats=len(returned) + len(released),
    )
    price_done = bool(price_given) or (
        configuration is not None
        and configuration.status in {'pending_sales'} | cfg_done_states
    )
    # §1: so'ralmagan va narxsiz qator ham yo'q — bu qadam bu zanjirda
    # ANIQ bo'lmaydi; so'ralmasdan o'tib ketilgan bo'lsa ham skipped
    has_priceless = bool(configuration and configuration.items_without_price)
    data['price_request'] = dict(
        done=bool(price_given),
        at=price_given[-1].created_at if price_given else None,
        who=price_given[-1].created_by if price_given else None,
        doc=('configuration', configuration),
        repeats=max(len(price_asked) - 1, 0),
        skipped=not price_asked and (
            price_done
            or (configuration is not None and not has_priceless)
        ),
        current_override=bool(price_asked and not price_given),
    )
    submitted_done = configuration is not None and (
        configuration.status in {'pending_sales'} | cfg_done_states
    )
    # 9-to'plam §1: aniqlashtirish aylanma, alohida qadam emas — joriy qadam
    # `submitted` bo'lib qolaveradi, lekin "kim kutilmoqda?" javobi sales
    clarifying = bool(
        configuration and configuration.status == 'pending_clarification'
    )
    questions = [
        a for a in approvals
        if a.decision == ConfigurationApproval.Decision.QUESTION
    ]
    data['submitted'] = dict(
        done=submitted_done,
        at=configuration.status_changed_at
        if configuration and configuration.status == 'pending_sales' else None,
        who=sales_owner if clarifying else engineer,
        role='sales' if clarifying else None,
        doc=('configuration', configuration),
        repeats=len(questions),
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
        # 12-§6: necha marta qaytgani — chiziqda "N marta qaytarildi"
        repeats=contract_rejections,
    )
    # 12-§1: sales -> bugalter -> admin -> Didox -> to'lov. Bugalter va
    # admin bu yerda ISHDAN (Didoxga yuborishdan) OLDIN so'raladi.
    bugalter_done = bool(
        contract and contract.status not in ('draft', 'rejected', 'cancelled', 'pending_bugalter')
    )
    data['bugalter_check'] = dict(
        done=bugalter_done,
        at=bugalter_rows[-1].created_at if bugalter_rows else None,
        who=bugalter_rows[-1].decided_by if bugalter_rows else None,
        doc=('contract', contract),
        # 20-§2.1: admin necha marta bugalterga qaytargani — chiziq
        # "admin N marta qaytardi" deb aniq gapirsin
        repeats=bugalter_returns,
    )
    admin_done = bool(
        contract and contract.status in (
            'ready_for_didox', 'pending_didox', 'approved', 'active', 'completed',
        )
    )
    admin_skipped = bool(
        admin_done and not admin_rows
        and any(a.decided_by_id is None for a in admin_auto)
    )
    # §2: summa ma'lum bo'lishi bilan qadam taqdiri ham ma'lum — chegaradan
    # past shartnomada admin bosqichi ANIQ bo'lmaydi (oldindan skipped)
    if contract is not None and not admin_done and not admin_skipped:
        from apps.sales.services import _admin_threshold_skip

        admin_skipped = _admin_threshold_skip(contract)
    data['admin_approve'] = dict(
        done=admin_done and not admin_skipped,
        at=admin_rows[-1].created_at if admin_rows else None,
        who=admin_rows[-1].decided_by if admin_rows else None,
        doc=('contract', contract),
        skipped=admin_skipped,
        # 10-to'plam §3: shartnoma AYNAN admin tasdig'ida turibdi — bu
        # "imkoniyat" emas, boshlangan ish; aks holda shartli qadam ustidan
        # sakrab, ish adminga "sizniki" bo'lib ko'rinmasdi
        current_override=bool(
            contract and contract.status == Contract.Status.PENDING_ADMIN
        ),
    )
    # 12-§6: rad etilgandan keyin `didox_sent_at`/`didox_accepted_at`
    # ESKI qiymatini saqlab qoladi — "bajarilgan" belgisi shu tufayli
    # oxirgi rad etishdan KEYIN bo'lgan bo'lishi shart, aks holda chiziq
    # o'tilmagan qadamni bajarilgan deb ko'rsatib, joriy qadamni sakratardi
    didox_sent_fresh = after_last_reject(contract.didox_sent_at if contract else None)
    didox_confirmed_fresh = after_last_reject(contract.didox_accepted_at if contract else None)
    data['didox_sent'] = dict(
        done=didox_sent_fresh,
        at=contract.didox_sent_at if contract else None,
        who=didox_rows[0].decided_by if didox_rows else None,
        doc=('contract', contract),
        # Juda eski yozuv: Didox ikki qadam kirishidan OLDINGI shartnoma —
        # zanjir o'tib ketgan (approved+) bo'lsa-yu hujjat hech qachon
        # bo'lmagan bo'lsa, bu qadam ANIQ bo'lmaydi
        skipped=bool(
            contract and not didox_sent_fresh
            and contract.status in ('approved', 'active', 'completed')
        ),
    )
    data['didox_confirmed'] = dict(
        done=didox_confirmed_fresh,
        at=contract.didox_accepted_at if contract else None,
        who=didox_rows[-1].decided_by if didox_rows else None,
        doc=('contract', contract),
        skipped=bool(
            contract and not didox_confirmed_fresh
            and contract.status in ('approved', 'active', 'completed')
        ),
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
    # §2: TLD ochilmagan bo'lsa qadam taqdiri `missing` dan ma'lum —
    # yetishmovchilik yo'q (yoki allaqachon yig'ilgan) bo'lsa ANIQ bo'lmaydi
    procurement_skipped = not tld_needed and (
        assembled
        or (configuration is not None and not configuration.missing_items)
    )
    data['procurement_sent'] = dict(
        done=tld_needed,
        at=replenishment.created_at if replenishment else None,
        who=replenishment.created_by if replenishment else None,
        # QOLGAN-ISHLAR #6: bu qadam AYNAN TLD yo'q paytda joriy bo'ladi —
        # ishning o'zi (hisob ochish) konfiguratsiya sahifasida bajariladi
        doc=('replenishment', replenishment) if replenishment else ('configuration', configuration),
        skipped=procurement_skipped,
        # 10-to'plam §3: to'lov keldi, yetishmovchilik bor, TLD hali
        # ochilmagan — ish ENGINEERDA ("Buyurtmachiga yuborish"); aks holda
        # chiziq bajarib bo'lmaydigan "Yig'ish"ni joriy deb ko'rsatardi
        current_override=bool(paid and not tld_needed and not procurement_skipped),
        # QOLGAN-ISHLAR #3: SLA hujjat holatidan emas, qadam HAQIQATAN
        # boshlangan paytdan — CFG `approved` bo'lib turgan payt emas
        since=first_payment.paid_at if first_payment else None,
    )
    tld_delivered = bool(
        replenishment and replenishment.status == Replenishment.Status.DELIVERED
    )
    # 10-to'plam §6: TLD qora quti emas — egasi (va nomi) TLD holatidan.
    # Aks holda mol bugalterni kutayotganda ham "buyurtmachida" deb turardi:
    # admin noto'g'ri javob olardi, SLA noto'g'ri odamga yozilardi, §5 dagi
    # hovuz qoidasi ham rolga tayanib noto'g'ri ishlardi.
    TLD_ACTOR = {
        Replenishment.Status.DRAFT: ('buyurtmachi', "TLD — to'ldirilmoqda"),
        Replenishment.Status.REJECTED: ('buyurtmachi', "TLD — to'ldirilmoqda"),
        Replenishment.Status.PENDING_SALES: ('sales', 'TLD — mijoz roziligi'),
        Replenishment.Status.PENDING_BUGALTER: ('bugalter', 'TLD — bugalter tekshiruvi'),
        Replenishment.Status.PENDING_ADMIN: ('admin', "TLD — admin tasdig'i"),
        Replenishment.Status.APPROVED: ('bugalter', "TLD — to'lov kutilmoqda"),
        Replenishment.Status.ORDERED: ('buyurtmachi', "TLD — yo'lda"),
        Replenishment.Status.IN_TRANSIT: ('buyurtmachi', "TLD — yo'lda"),
        Replenishment.Status.CUSTOMS: ('buyurtmachi', "TLD — yo'lda"),
    }
    tld_role, tld_label = (
        TLD_ACTOR.get(replenishment.status, (None, None))
        if replenishment else (None, None)
    )
    data['procurement_chain'] = dict(
        done=tld_delivered,
        at=replenishment.delivered_at if tld_delivered else None,
        who=None,
        role=tld_role,
        label=tld_label,
        doc=('replenishment', replenishment),
        skipped=procurement_skipped,
        # TLD ochiq — ish haqiqatan zanjir ichida ketmoqda: joriy shu yerda
        current_override=bool(replenishment and not tld_delivered),
        # QOLGAN-ISHLAR #3: TLD ochilgan paytdan — CFG holatidan emas
        since=replenishment.created_at if replenishment else None,
    )
    data['assemble'] = dict(
        done=assembled,
        at=configuration.assembled_at if configuration else None,
        who=engineer,
        doc=('configuration', configuration),
        # QOLGAN-ISHLAR #3: mol kelgan (TLD yetkazilgan) yoki to'lov kelgan
        # paytdan — ikkalasi ham "yig'ishga tayyor bo'lgan payt"ni aytadi.
        # `delivered_at` DateField — `_as_datetime` datetime'ga keltiradi
        since=_as_datetime(
            replenishment.delivered_at if tld_needed and replenishment
            else (first_payment.paid_at if first_payment else None)
        ),
    )
    finalized = bool(configuration and configuration.status in ('ready', 'sold'))
    data['finalize'] = dict(
        done=finalized,
        at=None,
        who=engineer,
        doc=('configuration', configuration),
        # QOLGAN-ISHLAR #3: yig'ilgan paytdan — CFG `approved` bo'lgan paytdan emas
        since=configuration.assembled_at if configuration else None,
    )

    # 14-§8: ko'p modelli savdoda `taken`dan keyingi model bosqichlari —
    # `submitted`/`sales_review`/`assemble`/`finalize` — savdo darajasida
    # ENG ORQADA qolgan model bo'yicha hisoblanadi: savdo "ko'rikka
    # yuborildi" emas, toki HAMMA model yuborilmaguncha. Shartnoma
    # ochilgandan keyingi qadamlar (u allaqachon bitta) tegilmaydi.
    # Bitta modelli savdoda (`deal_models` bo'sh) hech narsa o'zgarmaydi.
    from apps.configurator.services import _deal_models_for_request

    deal_models = _deal_models_for_request(request_obj)
    if len(deal_models) > 1:
        for key, pred in (
            ('submitted', lambda cfg: cfg.status in ({'pending_sales'} | cfg_done_states)),
            ('sales_review', lambda cfg: cfg.status in cfg_done_states),
            ('assemble', lambda cfg: bool(cfg.assembled_at)),
            ('finalize', lambda cfg: cfg.status in ('ready', 'sold')),
        ):
            all_done, lagging, models_block = _deal_step(deal_models, pred)
            data[key]['done'] = all_done
            data[key]['doc'] = ('configuration', lagging)
            data[key]['models'] = models_block

    # 20-§3.5: ACT — tarkib o'zgarishining moliyaviy asosi, bugalter
    # tasdig'idan o'tmaguncha `ship` qulflangan. Savdoda ACT bitta (14-§7)
    # — `_deal_step` kerak emas, qaror allaqachon savdo darajasida.
    act = configuration.act if configuration else None
    act_rows = list(act.approvals.all()) if act else []
    data['act_review'] = dict(
        done=bool(act and act.status == act.Status.APPROVED),
        at=act_rows[-1].created_at if act_rows else None,
        who=act_rows[-1].decided_by if act_rows else None,
        doc=('configuration', configuration),
        # Bugalter necha kundan buyon ushlab turibdi — SLA shu paytdan
        since=(
            act.status_changed_at
            if act and act.status == act.Status.PENDING_BUGALTER else None
        ),
    )

    data['ship'] = dict(
        done=delivered,
        at=contract.delivered_at if contract else None,
        # 10-§7: yetkazgan odam endi ma'lum — qadam ism oladi
        who=getattr(contract, 'delivered_by', None) if contract else None,
        doc=('contract', contract),
    )
    completed = bool(contract and contract.status == 'completed')
    # 11-to'plam §2: mol yetkazilgan-u qoldiq to'lanmagan bo'lsa, zanjirni
    # ochiq tutib turgan YAGONA narsa — pul, uni esa bugalter kiritadi.
    # Nom ham o'zgaradi: "Yakunlandi" kutish paytida "hammasi tugadi" degan
    # yolg'on taassurot berardi.
    awaiting_money = bool(
        contract and not completed and contract.delivered_at
        and contract.balance > 0
    )
    data['completed'] = dict(
        done=completed,
        at=contract.status_changed_at if completed and contract else None,
        who=None,
        role='bugalter' if awaiting_money else None,
        label="Qoldiq to'lov" if awaiting_money else None,
        doc=('contract', contract),
    )

    # 8-to'plam §1: zanjirda UMUMAN bo'lmaydigan hujjatning qadamlari
    # skipped — aks holda qo'lda ochilgan shartnoma "hali boshlanmagan"
    # ko'rinib, bosh sahifada tepaga chiqib ketardi. Hujjat "keyin paydo
    # bo'ladi"mi yoki "hech qachon bo'lmaydi"mi — buni faqat zanjir shakli
    # aytadi: keyingi bosqich hujjati bor-u, oldingisi yo'q bo'lsa,
    # oldingisi endi hech qachon paydo bo'lmaydi.
    missing_docs = set()
    if request_obj is None and (configuration is not None or contract is not None):
        missing_docs.add('request')
    if configuration is None and contract is not None:
        missing_docs.add('configuration')
    if missing_docs:
        for row in data.values():
            kind, _obj = row.get('doc') or (None, None)
            if kind in missing_docs:
                row['skipped'] = True
                row['current_override'] = False
        if 'configuration' in missing_docs:
            # TLD zanjiri konfiguratsiya orqali kuzatiladi — u ham yo'q
            for key in ('procurement_sent', 'procurement_chain'):
                data[key]['skipped'] = True
                data[key]['current_override'] = False

    # ---- joriy qadam va holatlar (§1/§3)
    # Tartib muhim: override birinchi (boshlangan ish doim g'olib — §3:
    # current_key hech qachon skipped qadamga ishora qilmasin), keyin
    # skipped o'tkaziladi, shartli (OPTIONAL) qadamlar esa "birinchi
    # bajarilmagan" qoidasidan chetda — ular ish emas, imkoniyat.
    current_key = None
    for key, _, _ in STEPS:
        row = data[key]
        if row.get('current_override') and not row.get('skipped'):
            current_key = key
            break
        if row.get('skipped'):
            continue
        if key in OPTIONAL:
            continue
        if not row['done']:
            current_key = key
            break

    profile = CompanyProfile.load()
    cutoff, days = profile.sla_cutoff_hour, profile.sla_working_days

    # SLA manbai — joriy bosqich qaysi hujjatda turgan bo'lsa o'sha.
    # QOLGAN-ISHLAR #3: bir nechta qadam bitta hujjat holati ichida ketma-ket
    # bajariladi (masalan CFG `approved` bo'lib turganda to'rtta qadam) —
    # `since` berilsa, u qadam HAQIQATAN boshlangan payt sifatida ustunlik qiladi
    def sla_for(doc_pair, since=None):
        kind, obj = doc_pair
        source = obj if obj is not None else (contract or configuration or request_obj)
        entered = since or (getattr(source, 'status_changed_at', None) if source else None)
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
                tone, waiting_days, deadline = sla_for((doc_kind, doc_obj), since=row.get('since'))
        else:
            # navbat kelmagan; 13–16 to'lovgacha qulf (B4) — blocked
            if key in PAYMENT_GATED and not paid and not row['done']:
                state, tone = 'blocked', 'muted'
            else:
                state, tone = 'pending', 'muted'

        actor_user = row.get('who')
        if state in ('pending', 'blocked'):
            actor_user = None  # kelajak qadamda ism yo'q — faqat rol
        # 9-to'plam §1 / 10-§6: qadam roli va nomi vaziyatga qarab o'zgaradi
        # (aniqlashtirishda `submitted` sales'ni kutadi; TLD qadami o'z
        # holatining egasini va qisqa nomini aytadi)
        role = row.get('role') or default_role
        label = row.get('label') or label
        steps.append({
            'key': key,
            'label': label,
            'state': state,
            'tone': tone,
            # §2: shartli qadam — front `skipped` ni chizmaydi, `pending`
            # bo'lsa xiraroq chizadi (bo'lishi mumkin, hali noma'lum)
            'optional': key in OPTIONAL,
            'actor': _actor(actor_user, role),
            'at': row.get('at'),
            'waiting_days': waiting_days if tone == 'danger' else None,
            'deadline': deadline,
            'document': _document(doc_kind, doc_obj),
            'can_open': _can_open(user, doc_kind, doc_obj, contract),
            'repeats': row.get('repeats', 0),
            # 14-§8: ko'p modelli savdoda {done, total, pending}; aks holda null
            'models': row.get('models'),
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
