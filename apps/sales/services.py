import re
from decimal import Decimal

from django.db.models import Max, Sum
from django.db.transaction import atomic
from django.utils.timezone import localdate, now
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.core.models import Notification
from apps.finance.services import record_transaction
from apps.sales.models import Contract, ContractApproval, ContractItem, ContractPayment, Lead


def _didox_valid_for_current_cycle(contract):
    """QOLGAN-ISHLAR #1: eski yozuv moslik sharti §6 bilan zid ishlagan.

    `didox_accepted_at` rad etishda TOZALANMAYDI (§6 — sana tarixiy iz).
    Shuning uchun "Didox allaqachon bo'lgan" savoliga shu maydonning
    o'zi emas, u OXIRGI RAD ETISHDAN KEYIN bo'lganimi javob berishi
    kerak — aks holda rad etilib qayta boshlangan shartnoma eski
    (endi haqiqiy emas) Didox izidan to'g'ridan `approved`ga sakraydi
    va mijozdan hujjatsiz pul so'raladi (jonli holat: SHT-00058).
    """
    if not contract.didox_accepted_at:
        return False
    last_reject_at = contract.approvals.filter(
        decision=ContractApproval.Decision.REJECTED,
    ).aggregate(m=Max('created_at'))['m']
    return last_reject_at is None or contract.didox_accepted_at > last_reject_at


def link_lead_to_contract(contract):
    """Mijozning ochiq kelishuvini shartnomaga bog'laydi (§10.8).

    Kelishuv quvuri avtomatik yopiladi: shartnoma tuzilgach lead
    `contract` bosqichiga o'tadi va konversiya hisobotida ko'rinadi.
    """
    if not contract.client_id:
        return None
    lead = (
        Lead.objects
        .filter(client=contract.client, contract__isnull=True)
        .exclude(stage__in=[Lead.Stage.CONTRACT, Lead.Stage.LOST])
        .order_by('-created_at')
        .first()
    )
    if lead is None:
        return None
    lead.contract = contract
    lead.stage = Lead.Stage.CONTRACT
    lead.save(update_fields=['contract', 'stage'])
    return lead


@atomic
def create_contract_from_configuration(configuration, user, client=None):
    """Konfiguratsiyadan avtomatik draft shartnoma ochadi.

    YANGI OQIM (B1): sales texnik yechimni tasdiqlaganda chaqiriladi —
    shartnoma zanjir BOSHIDA ochiladi, mol esa to'lovdan keyin tayyorlanadi.
    Mijoz: berilgan `client`, bo'lmasa konfiguratsiyadagi, bo'lmasa
    zayavkadagi (ZVK) mijoz. Mijoz aniqlanmasa shartnoma ochilmaydi (None) —
    approve bosqichi buni 400 bilan ushlaydi (B10).

    Qator: tayyor variant (odatda hali yo'q — bazaviy model), narxi
    konfiguratsiya narxidan (QQS'siz), QQS default foiz bilan. `finalize`
    da qator yig'ilgan variantga ko'chadi (B6) — son va narx tegilmaydi.
    """
    existing = (
        Contract.objects.filter(configuration=configuration)
        .exclude(status__in=[Contract.Status.REJECTED, Contract.Status.CANCELLED])
        .first()
    )
    if existing:
        return existing

    request_obj = (
        configuration.requests.filter(created_by__isnull=False)
        .order_by('-created_at').first()
    )
    if client is None and configuration.client_id:
        client = configuration.client
    if client is None:
        client_request = (
            configuration.requests.filter(client__isnull=False)
            .order_by('-created_at').first()
        )
        client = client_request.client if client_request else None
    if client is None:
        return None

    # EGALIK §3.2: avtomatik shartnomaning egasi — zayavkani yozgan SALES
    # (finalize'ni engineer bosadi, lekin shartnoma sales'niki bo'lishi kerak,
    # aks holda u o'z shartnomasini ko'rmay qolardi)
    owner = request_obj.created_by if request_obj else user

    contract = Contract.objects.create(
        client=client,
        configuration=configuration,
        note=f'{configuration.number} konfiguratsiyasi asosida avtomatik ochildi',
        created_by=owner,
    )
    ContractItem.objects.create(
        contract=contract,
        product=configuration.variant or configuration.base_product,
        # #3: partiya — mijoz nechta so'ragan bo'lsa shuncha; narx bitta donaga
        quantity=configuration.quantity,
        unit_price=configuration.total_price,
        # 12-§2 (C): qator aynan shu modeldan kelgani belgilanadi
        configuration=configuration,
    )
    contract.total_amount = contract.items_total_with_vat
    contract.prepayment_percent = None
    contract.save()

    # §11.4/B5: bron sinxroni — konfiguratsiya tayyor bo'lmaguncha bu
    # chaqiruv hech narsa qilmaydi (molni CFG ushlab turadi), keyin esa
    # variantni qattiq band qiladi
    from apps.inventory.services import sync_contract_reservations

    sync_contract_reservations(contract)

    # §10.8: mijozning ochiq kelishuvi shartnomaga bog'lanadi. Zayavka esa
    # ARXIVLANMAYDI (B7): u zanjir umurtqasi — shartnoma yakunlanganda
    # (`completed`) arxivga o'tadi, 12 qadam oldin emas (§3.5).
    link_lead_to_contract(contract)
    return contract


def archive_completed_chain(contract):
    """SHT yakunlandi — zayavka endi arxivga o'tadi (B7, §3.5).

    Zanjir 19-qadamda tugaydi; ungacha ZVK ro'yxatlarda ko'rinib, roadmap
    umurtqasi bo'lib turadi. 12-§2 (C): bitta shartnomada bir nechta model
    bo'lishi mumkin — HAMMASINING zayavkasi arxivlanadi, faqat birinchisiniki
    emas (`contract.configuration` — zanjirning birinchi modeli).
    """
    from apps.configurator.models import ConfigurationRequest

    if contract.status != Contract.Status.COMPLETED:
        return
    config_ids = set(
        contract.items.exclude(configuration__isnull=True)
        .values_list('configuration_id', flat=True)
    )
    if contract.configuration_id:
        config_ids.add(contract.configuration_id)
    if not config_ids:
        return
    ConfigurationRequest.objects.filter(
        configuration_id__in=config_ids, status=ConfigurationRequest.Status.DONE,
    ).update(status=ConfigurationRequest.Status.ARCHIVED)


def _notify_role(role, contract, title, message, level=Notification.Level.WARNING):
    """Bosqich egasiga (roldagi barcha faol foydalanuvchilarga) eslatma."""
    from apps.accounts.models import User

    for recipient in User.objects.filter(role=role, is_active=True):
        Notification.objects.create(
            user=recipient,
            title=title,
            message=message,
            level=level,
            entity='Contract',
            object_id=str(contract.pk),
        )


def _require_role(user, *, bugalter=False, admin=False, sales=False):
    if not user or not user.is_authenticated:
        raise PermissionDenied('Avtorizatsiya talab qilinadi.')
    if user.is_admin:
        return
    if bugalter and user.is_bugalter:
        return
    if sales and user.is_sales:
        return
    if admin:
        raise PermissionDenied('Bu bosqichni faqat admin tasdiqlaydi.')
    raise PermissionDenied('Bu amal uchun ruxsat yo\'q.')


@atomic
def _contract_deal_request(contract):
    """14-§4: shartnoma ortidagi savdo (ZVK) — bog'langan istalgan model orqali.

    `contract.configuration` — savdoning birinchi modeli (bo'lmasligi
    mumkin, masalan ombordan to'g'ridan sotuvda); topilmasa qatorlar
    orqali ham qidiriladi (`ContractItem.configuration`, 12-§2 C).
    """
    from apps.configurator.services import _owning_request

    if contract.configuration_id:
        request_obj = _owning_request(contract.configuration)
        if request_obj is not None:
            return request_obj
    item = (
        contract.items.filter(configuration__isnull=False)
        .select_related('configuration').first()
    )
    return _owning_request(item.configuration) if item else None


def submit_contract(contract, user):
    """Sales shartnomani bugalter tasdig'iga yuboradi."""
    _require_role(user, sales=True)
    # EGALIK §3.4: istalgan sales emas — faqat egasi yuboradi (admin istisno;
    # egasiz eski yozuvni bloklamaymiz)
    if (
        not user.is_admin
        and contract.created_by_id
        and contract.created_by_id != user.id
    ):
        raise PermissionDenied('Bu shartnoma sizniki emas — faqat egasi yuboradi.')
    # Rad etilgan shartnoma tuzatilib qayta yuboriladi (TLD dagi kabi)
    if contract.status not in {Contract.Status.DRAFT, Contract.Status.REJECTED}:
        raise ValidationError('Faqat qoralama shartnoma yuboriladi.')
    if not contract.items.exists():
        raise ValidationError('Shartnoma qatorlari kiritilmagan.')
    # 21-§3.6: shablonsiz/matnsiz shartnoma yuborilmaydi
    document = get_or_create_contract_document(contract)
    if not (document.body or '').strip():
        raise ValidationError({
            'detail': 'Shartnoma matni bo\'sh — shablon tanlang.',
        })

    # 14-§4: savdoda (ZVK) tugamagan model bo'lsa yuborilmaydi — aks holda
    # ikkinchi modelning boradigan joyi qolmaydi. Majburlash yo'q (`force`
    # yo'q) — bitta modelli zayavkada bu tekshiruv hech narsa qilmaydi.
    from apps.configurator.models import ConfigurationRequestLine
    from apps.configurator.services import deal_has_multiple_models

    request_obj = _contract_deal_request(contract)
    if deal_has_multiple_models(request_obj):
        pending = []
        if not request_obj.primary_line_done and request_obj.configuration_id:
            pending.append(request_obj.configuration)
        pending += [
            line.configuration
            for line in request_obj.lines.filter(
                kind=ConfigurationRequestLine.Kind.MODEL, configuration__isnull=False,
            ).select_related('configuration')
            if not line.is_complete
        ]
        if pending:
            raise ValidationError({
                'detail': (
                    f'{request_obj.number} da yana {len(pending)} ta model '
                    "tayyor emas — hammasi tasdiqlangach yuboring."
                ),
                'pending_models': [
                    {
                        'id': cfg.id, 'number': cfg.number,
                        'status': cfg.status, 'status_display': cfg.get_status_display(),
                    }
                    for cfg in pending
                ],
            })

    contract.status = Contract.Status.PENDING_BUGALTER
    contract.save()
    # §11.4: muddat o'tib bron bo'shagan bo'lsa, yuborishda qayta band qilinadi
    from apps.inventory.services import sync_contract_reservations

    sync_contract_reservations(contract)
    from apps.accounts.models import User

    _notify_role(
        User.Role.BUGALTER, contract,
        title=f'{contract.number}: shartnoma tekshiruvga keldi',
        message=(
            f'Sales yubordi. Summa: {contract.total_amount} {contract.currency} — '
            'tekshirib tasdiqlang, keyin adminga o\'tadi.'
        ),
    )
    return contract


def _admin_threshold_skip(contract):
    """§11.3: chegaradan kichik UZS shartnoma admin tasdig'isiz o'tadimi.

    Chegara `CompanyProfile.admin_approval_threshold` (QQS bilan solishtiriladi,
    0 — chegara yo'q). Boshqa valyutadagi shartnoma doim adminga boradi —
    shartnomada kurs yo'q, chegara esa so'mda.
    """
    from apps.core.models import CompanyProfile

    threshold = CompanyProfile.load().admin_approval_threshold
    return bool(
        threshold and contract.currency == 'UZS' and contract.total_amount < threshold
    )


@atomic
def approve_contract(contract, user, comment=''):
    """Bugalter -> admin zanjiri bo'yicha tasdiqlash — Didoxdan OLDIN (12-§1).

    Admin tasdig'i — RUXSAT, shuning uchun ishdan (Didoxga yuborishdan)
    oldin so'raladi: sales -> bugalter -> admin -> Didox -> to'lov.
    §11.3: summa chegaradan kichik bo'lsa admin bosqichi o'tkazib yuboriladi
    (tarixda avtomatik yozuv qoladi) — u holda ham Didox hali oldinda.
    """
    admin_skipped = False
    if contract.status == Contract.Status.PENDING_BUGALTER:
        _require_role(user, bugalter=True)
        step = ContractApproval.Step.BUGALTER
        # Chop etish shaklida sana bo'sh qolmasin — tekshiruv kuni imzo sanasi
        if not contract.signed_at:
            contract.signed_at = localdate()
        admin_skipped = _admin_threshold_skip(contract)
        contract.status = (
            Contract.Status.READY_FOR_DIDOX if admin_skipped
            else Contract.Status.PENDING_ADMIN
        )
    elif contract.status == Contract.Status.PENDING_ADMIN:
        _require_role(user, admin=True)
        step = ContractApproval.Step.ADMIN
        # 12-§1 eski yozuvlar: eski tartibda (Didoxdan keyin admin) ketgan
        # shartnomaning Didoxi allaqachon tasdiqlangan bo'lishi mumkin —
        # ikkinchi marta Didoxga yuborilmasin, to'g'ridan approved.
        # QOLGAN-ISHLAR #1: lekin faqat shu JORIY aylanishda — rad etilib
        # qayta boshlangan bo'lsa eski Didox izi endi haqiqiy emas
        contract.status = (
            Contract.Status.APPROVED if _didox_valid_for_current_cycle(contract)
            else Contract.Status.READY_FOR_DIDOX
        )
    else:
        raise ValidationError('Shartnoma tasdiqlash bosqichida emas.')

    contract.save()
    # 4-to'plam §4: qaror qabul qilindi — bajargan odamning eslatmasi yopiladi
    from apps.core.services import resolve_notifications

    resolve_notifications('Contract', contract.pk, user=user)
    ContractApproval.objects.create(
        contract=contract,
        step=step,
        decision=ContractApproval.Decision.APPROVED,
        comment=comment,
        decided_by=user,
    )
    if admin_skipped:
        _record_admin_skip(contract)
    _notify_after_bugalter_stage(contract, admin_skipped)
    return contract


def _record_admin_skip(contract):
    """§11.3: tarix jim qolmasin — nega admin ko'rmagani yozib qo'yiladi."""
    from apps.core.models import CompanyProfile

    threshold = CompanyProfile.load().admin_approval_threshold
    ContractApproval.objects.create(
        contract=contract,
        step=ContractApproval.Step.ADMIN,
        decision=ContractApproval.Decision.APPROVED,
        comment=(
            f'Summa {contract.total_amount} {contract.currency} — '
            f'chegara {threshold} dan past, admin tasdig\'i talab qilinmadi.'
        ),
        decided_by=None,
    )


def _notify_after_bugalter_stage(contract, admin_skipped):
    """Bugalter bosqichidan keyingi bildirishnomalar — approve ikkalasi ham
    (bugalter va admin) shu yerdan (bitta matn, ikki xil haqiqat bo'lmasin).

    12-§1: admin ruxsati endi Didoxdan OLDIN, ya'ni tasdiqdan keyingi holat
    doim `ready_for_didox` — "pul kutilmoqda" xabari `confirm_didox`ga ko'chdi.
    """
    from apps.accounts.models import User

    if contract.status == Contract.Status.PENDING_ADMIN:
        _notify_role(
            User.Role.ADMIN, contract,
            title=f'{contract.number}: admin tasdig\'i kutilmoqda',
            message=(
                f'Bugalter tekshirib tasdiqladi. Summa: {contract.total_amount} '
                f'{contract.currency} — oxirgi tasdiq sizdan.'
            ),
        )
    elif contract.status == Contract.Status.READY_FOR_DIDOX:
        if admin_skipped:
            didox_message = (
                "Summa chegaradan past — admin tasdig'i talab qilinmadi. "
                'Endi Didoxga yuboring.'
            )
            creator_message = (
                'Bugalter tasdiqladi (summa chegaradan past — admin shart emas) '
                '— Didoxga yuborilishi kutilmoqda.'
            )
        else:
            didox_message = 'Admin tasdiqladi — endi Didoxga yuboring.'
            creator_message = 'Bugalter va admin tasdiqladi — Didoxga yuborilishi kutilmoqda.'
        _notify_role(
            User.Role.BUGALTER, contract,
            title=f'{contract.number}: tasdiqlandi — Didoxga yuboring',
            message=didox_message,
        )
        if contract.created_by:
            Notification.objects.create(
                user=contract.created_by,
                title=f'{contract.number}: shartnoma tasdiqlandi',
                message=creator_message,
                level=Notification.Level.INFO,
                entity='Contract',
                object_id=str(contract.pk),
            )
    elif contract.status == Contract.Status.APPROVED:
        # Eski yozuvlar: Didoxi allaqachon tasdiqlangan bo'lib admin shu
        # yerda to'g'ridan-to'g'ri approved qiladi — pul kutilmoqda xabari
        _notify_payment_awaited(contract)
    return contract


def _notify_payment_awaited(contract):
    """Tasdiqlandi, Didox ham tasdiqlandi — endi pul kutilmoqda.

    `confirm_didox` (normal yo'l) va `approve_contract` (eski, Didoxi
    allaqachon tasdiqlangan yozuv) ikkalasi ham shu yerdan chaqiradi.
    """
    from apps.accounts.models import User

    pay_message = (
        f"Oldindan to'lov {contract.prepayment_percent}% — "
        f'{contract.prepayment_amount} {contract.currency}. '
        'Pul kelgach confirm-payment qiling.'
    )
    _notify_role(
        User.Role.BUGALTER, contract,
        title=f'{contract.number}: tasdiqlandi — pul kutilmoqda',
        message=pay_message,
    )
    if contract.created_by:
        Notification.objects.create(
            user=contract.created_by,
            title=f'{contract.number}: shartnoma tasdiqlandi',
            message="Didox tasdiqlandi — mijozdan to'lov kutilmoqda.",
            level=Notification.Level.INFO,
            entity='Contract',
            object_id=str(contract.pk),
        )


@atomic
def send_didox(contract, user, didox_number):
    """Bugalter shartnomani Didoxga yubordi (B3, 1-qadam).

    Uch harakatning ikkinchisi: ko'rdi → **Didoxga yubordi** → Didox
    tasdiqladi. Raqam majburiy; holat `pending_didox` — mijoz imzosi
    kutilmoqda. Orqaga yo'l yo'q: Didox rad etsa bu bizning omilimiz emas,
    mijoz Didoxning o'zida qayta yuboradi.
    """
    _require_role(user, bugalter=True)
    if contract.status != Contract.Status.READY_FOR_DIDOX:
        raise ValidationError({
            'detail': "Avval bugalter va admin tasdig'i olinsin — keyin Didox.",
        })
    didox_number = (didox_number or '').strip()
    if not didox_number:
        raise ValidationError({'didox_number': 'Didox raqami majburiy.'})

    contract.didox_number = didox_number
    contract.didox_sent_at = now()
    # Chop etish shaklida sana bo'sh qolmasin — yuborish kuni imzo sanasi
    if not contract.signed_at:
        contract.signed_at = localdate()
    contract.status = Contract.Status.PENDING_DIDOX
    contract.save()

    from apps.core.services import resolve_notifications

    resolve_notifications('Contract', contract.pk, user=user)
    ContractApproval.objects.create(
        contract=contract,
        step=ContractApproval.Step.DIDOX,
        decision=ContractApproval.Decision.APPROVED,
        comment=f'Didoxga yuborildi: {didox_number}',
        decided_by=user,
    )
    if contract.created_by:
        Notification.objects.create(
            user=contract.created_by,
            title=f'{contract.number}: Didoxga yuborildi',
            message=f'Raqam: {didox_number}. Mijoz imzosi kutilmoqda.',
            level=Notification.Level.INFO,
            entity='Contract',
            object_id=str(contract.pk),
        )
    return contract


@atomic
def confirm_didox(contract, user, comment=''):
    """Didox tasdiqlandi — mijoz imzoladi (B3, 2-qadam), bugalter belgilaydi.

    12-§1: admin ruxsati endi Didoxdan OLDIN olingan (`approve_contract`),
    shuning uchun bu qadam chegarani bilmaydi — natija doim `approved`.
    """
    _require_role(user, bugalter=True)
    if contract.status != Contract.Status.PENDING_DIDOX:
        raise ValidationError({
            'detail': 'Shartnoma Didox tasdig\'ini kutish bosqichida emas.',
        })

    contract.didox_accepted_at = now()
    contract.status = Contract.Status.APPROVED
    contract.save()

    from apps.core.services import resolve_notifications

    resolve_notifications('Contract', contract.pk, user=user)
    ContractApproval.objects.create(
        contract=contract,
        step=ContractApproval.Step.DIDOX,
        decision=ContractApproval.Decision.APPROVED,
        comment=comment or 'Didox tasdiqlandi — mijoz imzoladi.',
        decided_by=user,
    )
    _notify_payment_awaited(contract)
    return contract


@atomic
def reject_contract(contract, user, comment='', target='sales'):
    """Bugalter yoki admin shartnomani rad etadi — ikki manzil (20-§2).

    `target='sales'` (standart, hozirgi xulq) — chernovikka qaytadi.
    `target='bugalter'` — FAQAT admin, FAQAT `pending_admin`dan: admin
    hujjatdagi xatoni (Didox raqami, rekvizit — ko'pincha bugalterniki)
    ko'rib, sales'ni bekorga oraga qo'ymay to'g'ridan bugalterga
    qaytaradi. Ikki bosqich o'rniga bitta: admin → bugalter → admin.
    """
    if target not in ('sales', 'bugalter'):
        raise ValidationError({'target': f"Noma'lum manzil: {target}."})

    # target='bugalter' — ruxsat STATUSdan mustaqil, FAQAT admin: bugalter
    # o'ziga qaytara olmaydi (403, hali status tekshirilmasdan)
    if target == 'bugalter':
        _require_role(user, admin=True)

    if contract.status == Contract.Status.PENDING_BUGALTER:
        _require_role(user, bugalter=True)
        step = ContractApproval.Step.BUGALTER
        if target == 'bugalter':
            raise ValidationError({
                'detail': 'Shartnoma allaqachon bugalterda.',
            })
    elif contract.status == Contract.Status.PENDING_ADMIN:
        _require_role(user, admin=True)
        step = ContractApproval.Step.ADMIN
    else:
        raise ValidationError('Shartnoma tasdiqlash bosqichida emas.')

    contract.status = (
        Contract.Status.PENDING_BUGALTER if target == 'bugalter'
        else Contract.Status.REJECTED
    )
    contract.save()
    # 4-to'plam §4: qaror qabul qilindi — bajargan odamning eslatmasi yopiladi
    from apps.core.services import resolve_notifications

    resolve_notifications('Contract', contract.pk, user=user)
    ContractApproval.objects.create(
        contract=contract,
        step=step,
        decision=ContractApproval.Decision.REJECTED,
        comment=comment,
        decided_by=user,
        returned_to=target if target == 'bugalter' else '',
    )
    if target == 'bugalter':
        from apps.accounts.models import User

        _notify_role(
            User.Role.BUGALTER, contract,
            title=f'{contract.number}: admin bugalterga qaytardi',
            message=(
                f'{comment}\nTuzatib qayta tasdiqlang — shartnoma yana adminga boradi.'
                if comment else
                'Tuzatib qayta tasdiqlang — shartnoma yana adminga boradi.'
            ),
        )
    elif contract.created_by:
        Notification.objects.create(
            user=contract.created_by,
            title=f'{contract.number}: shartnoma qaytarildi',
            message=comment,
            level=Notification.Level.WARNING,
            entity='Contract',
            object_id=str(contract.pk),
        )
    # §11.4: rad etilgan shartnoma molni ushlab turmaydi — bron bo'shaydi
    # (sales tuzatib qayta yuborsa, submit'da qayta band qilinadi). Admin
    # bugalterga qaytarganda (target='bugalter') bron TURAVERADI — bu hali
    # rad etish emas, hujjat ustida ichki tekshiruv (sync bari bir holatga
    # mos: PENDING_BUGALTER qayta band qiladi, natija o'zgarmaydi).
    from apps.inventory.services import sync_contract_reservations

    sync_contract_reservations(contract)
    return contract


def _ship_contract_items(contract, user):
    """Sotilgan mahsulotlarni ombordan chiqim qiladi (TZ 3.1, 9).

    Birinchi to'lov tasdiqlanganda har bir shartnoma qatori bo'yicha
    ombor qoldig'i kamayadi. Ombor hali sozlanmagan bo'lsa (bo'sh tizim)
    harakat yozilmaydi.

    21-§1.3: konfiguratsiyali qator — agar yig'ishda haqiqatan narsa
    iste'mol qilingan bo'lsa (butlovchilar yoki modify — bunda
    `configuration.variant` bo'sh qoladi), mol allaqachon chiqqan, ship'da
    ikkinchi marta chiqarilmaydi. Faqat tarkib zavod standartiga teng
    bo'lgan holatda (`variant` = bazaviy modelning o'zi) ship oddiy
    qatordek ombordan chiqaradi.
    """
    from apps.inventory.models import StockMovement, Warehouse
    from apps.inventory.services import apply_movement, sellable_quantity

    # Biznesda bitta ombor — chiqim doim yagona ombordan
    warehouse = Warehouse.objects.filter(is_active=True).order_by('id').first()
    if warehouse is None:
        return

    # §11.4 eng nozik joy: erkin qoldiq + SHU zanjirning o'z broni —
    # aks holda shartnoma o'zi (yoki konfiguratsiyasi) band qilgan molga
    # o'zi yetisha olmay qolardi (B5: to'langan CFG broni ham QATTIQ)
    def _open(product):
        return sellable_quantity(
            product, warehouse,
            for_contract=contract,
            for_configuration=contract.configuration,
        )

    items = [
        item for item in contract.items.select_related('product', 'configuration')
        if not item.configuration_id or item.configuration.variant_id
    ]

    shortages = [
        f'{item.product.name} (kerak: {item.quantity}, '
        f'sotuvga ochiq: {_open(item.product)})'
        for item in items
        if _open(item.product) < item.quantity
    ]
    if shortages:
        raise ValidationError({
            'detail': 'Omborda sotish uchun mahsulot yetarli emas.',
            'items': shortages,
        })

    for item in items:
        apply_movement(
            product=item.product,
            warehouse=warehouse,
            type=StockMovement.Type.OUT,
            quantity=item.quantity,
            reason=StockMovement.Reason.SALE,
            reference=contract.number,
            user=user,
        )


@atomic
def confirm_payment(contract, user, *, amount, method=ContractPayment.Method.TRANSFER,
                    paid_at=None, is_prepayment=None):
    """Bugalter pul kelganini tasdiqlaydi — shu kundan muddat sanog'i boshlanadi.

    Birinchi to'lovda sotilgan mahsulotlar ombordan chiqim qilinadi (TZ 9).
    """
    _require_role(user, bugalter=True)
    if contract.status not in {Contract.Status.APPROVED, Contract.Status.ACTIVE}:
        raise ValidationError('Avval shartnoma admin tomonidan tasdiqlanishi kerak.')

    # 4-to'plam §3: summa chegarasi — kassaga yo'q pul yozilmasin.
    # /contract-payments/ ham shu yo'ldan o'tadi, ya'ni himoya bitta joyda.
    amount = Decimal(str(amount))
    if amount <= 0:
        raise ValidationError({
            'amount': "To'lov summasi noldan katta bo'lishi kerak.",
        })
    # Eski manfiy balansli shartnoma 500 emas, tushunarli 400 olsin
    balance = max(contract.balance, Decimal('0'))
    if amount > balance:
        raise ValidationError({
            'amount': (
                f"To'lov qoldiqdan ko'p: qoldiq {balance} {contract.currency}. "
                "Ortiqcha to'lov shartnomaga yozilmaydi — qaytarish yoki avans "
                "alohida hujjat bilan rasmiylashtiriladi."
            ),
        })

    paid_at = paid_at or now()
    first_payment = contract.status == Contract.Status.APPROVED
    if is_prepayment is None:
        is_prepayment = first_payment

    # TOPSHIRIQ-2 #2: to'lovda mol CHIQMAYDI — chiqim alohida `ship` hodisasi.
    # Shu tufayli "90 kun ichida yetkazamiz" haqiqiy ma'no oladi va omborda
    # hali to'lmagan shartnoma to'lovda qotib qolmaydi (bron ushlab turadi).

    payment = ContractPayment.objects.create(
        contract=contract,
        amount=amount,
        method=method,
        paid_at=paid_at,
        is_prepayment=is_prepayment,
        created_by=user,
        approved_by=user,
    )
    # §11.2: bugalterning 2-bosqichi ham tarixga tushadi — "to'lovni qabul qildim"
    # (Step.PAYMENT modelda azaldan bor edi, lekin hech qayerda yozilmasdi)
    ContractApproval.objects.create(
        contract=contract,
        step=ContractApproval.Step.PAYMENT,
        decision=ContractApproval.Decision.APPROVED,
        comment=f"To'lov qabul qilindi: {amount} {contract.currency}",
        decided_by=user,
    )
    record_transaction(
        code='sale',
        amount=amount,
        occurred_at=paid_at,
        description=f'{contract.number} bo\'yicha to\'lov',
        currency=contract.currency,
        contract=contract,
        user=user,
        approved_by=user,
    )

    if first_payment:
        # localdate: yarim tunda UTC sana bilan mahalliy sana farq qiladi
        contract.start_date = localdate(paid_at)
        contract.status = Contract.Status.ACTIVE
        # §10.8: konfiguratsiya terminal holatga o'tadi — zanjir yopildi
        if contract.configuration_id:
            from apps.configurator.models import Configuration

            Configuration.objects.filter(
                pk=contract.configuration_id,
                status=Configuration.Status.READY,
            ).update(status=Configuration.Status.SOLD)
    # #2-Q5: balans nolga tushsa ham YETKAZILMAGUNCHA yopilmaydi
    if contract.balance <= 0 and contract.delivered_at:
        contract.status = Contract.Status.COMPLETED
    contract.save()

    # YANGI-OQIM B5.3: pul keldi — konfiguratsiya broni yumshoqdan qattiqqa
    # ko'chadi (endi "rejada" emas, "band") va ish boshlanish signali beriladi
    if first_payment and contract.configuration_id:
        from apps.inventory.services import sync_configuration_reservations

        sync_configuration_reservations(contract.configuration)
        if contract.configuration.created_by:
            Notification.objects.create(
                user=contract.configuration.created_by,
                title=f'{contract.configuration.number}: to\'lov keldi — ish boshlanadi',
                message=(
                    f'{contract.number} bo\'yicha boshlang\'ich to\'lov qabul '
                    'qilindi. Endi yetishmaganini buyurtmachiga yuborish va '
                    'yig\'ish ochiq.'
                ),
                level=Notification.Level.INFO,
                entity='Configuration',
                object_id=str(contract.configuration.pk),
            )

    archive_completed_chain(contract)
    # 4-to'plam §4: "to'lovni qabul qiling" vazifasi bajarildi
    from apps.core.services import resolve_notifications

    resolve_notifications('Contract', contract.pk, user=user)
    return payment


def _unapproved_acts(contract):
    """20-§3.4: shartnoma qatorlari ortidagi, hali tasdiqlanmagan ACTlar.

    Konfiguratsiyasiz qatorlarda (`kind=item`, sales qo'lda ochgan
    shartnoma) `configuration_id` bo'sh — ularga ACT tegishli emas.
    """
    from apps.configurator.models import Act

    acts = {
        item.configuration.act
        for item in contract.items.select_related('configuration__act')
        if item.configuration_id and item.configuration.act_id
    }
    return [a for a in acts if a.status != Act.Status.APPROVED]


@atomic
def ship_contract(contract, user):
    """Yetkazib berish (#2): mol AYNAN shu yerda ombordan chiqadi.

    Kim: shartnoma egasi sales (va admin) — mijoz bilan gaplashadigan,
    molni topshiradigan odam (11-§3). Buyurtmachi va bugalter mol bilan
    ishlamaydi — ular zanjirning boshqa uchida (TLD, pul).
    Shartlari: boshlang'ich to'lov qabul qilingan (`active`), hali
    yetkazilmagan, mol yetarli (o'z broni o'ziga ochiq). Bir marta, to'liq —
    qisman yetkazish hozircha yo'q. Balans yopiq bo'lsa shu yerda `completed`.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied('Avtorizatsiya talab qilinadi.')
    if not user.is_admin:
        if not user.is_sales:
            raise PermissionDenied("Yetkazishni sales (shartnoma egasi) belgilaydi.")
        if contract.created_by_id and contract.created_by_id != user.id:
            raise PermissionDenied('Bu shartnoma sizniki emas.')
    if contract.delivered_at:
        raise ValidationError({'detail': 'Bu shartnoma allaqachon yetkazilgan.'})
    if contract.status not in {Contract.Status.ACTIVE, Contract.Status.COMPLETED}:
        raise ValidationError({
            'detail': "Avval boshlang'ich to'lov qabul qilinsin — yetkazish faol shartnomada.",
        })

    # 20-§3.4: ACT — tarkib o'zgarishining moliyaviy asosi, bugalter
    # tasdig'idan o'tmaguncha mol chiqmasin. Konfiguratsiyasiz qator
    # (tayyor tovar, `kind=item`) yoki sales qo'lda ochgan shartnomada
    # `configuration_id` bo'sh — to'plam bo'sh, yetkazish bugungidek o'tadi.
    pending_acts = _unapproved_acts(contract)
    if pending_acts:
        raise ValidationError({
            'detail': "ACT bugalter tasdig'idan o'tmagan — mol chiqarilmaydi.",
            'acts': [
                {'id': a.id, 'number': a.number, 'status': a.status}
                for a in pending_acts
            ],
        })

    _ship_contract_items(contract, user)
    # §11.4: bron chiqimga aylandi
    from apps.inventory.services import mark_reservations_shipped

    mark_reservations_shipped(contract)

    contract.delivered_at = localdate()
    # 10-§7: kim yetkazgani yozib qo'yiladi — u shartnomani yopilguncha
    # ko'rib turadi (StockMovement'dan qazib olish shart emas)
    contract.delivered_by = user
    if contract.balance <= 0:
        contract.status = Contract.Status.COMPLETED
    contract.save()
    archive_completed_chain(contract)

    # 4-to'plam §4: "yetkazing" vazifasi bajarildi — yetkazgan odamniki yopiladi
    from apps.core.services import resolve_notifications

    resolve_notifications('Contract', contract.pk, user=user)

    if contract.created_by:
        Notification.objects.create(
            user=contract.created_by,
            title=f'{contract.number}: yetkazildi',
            message='Mol mijozga chiqim qilindi — mijozga xabar berishingiz mumkin.',
            level=Notification.Level.INFO,
            entity='Contract',
            object_id=str(contract.pk),
        )
    return contract


@atomic
def send_contract_missing_to_procurement(contract, user):
    """Shartnomadan buyurtmachiga (#2): band qilinmagan qismidan TLD ochadi.

    `kerak − band qilingan` bo'yicha yetishmayotgan qatorlar chernovik TLD
    bo'ladi: `contract` FK bog'lanadi, `owner_sales` — shartnoma egasi;
    bitta ochiq TLD qoidasi amal qiladi. Kim bosadi: sales (egasi) — u
    mijozga muddat aytadi.
    """
    from apps.accounts.models import User
    from apps.inventory.models import StockReservation
    from apps.inventory.services import main_warehouse
    from apps.procurement.models import Replenishment, ReplenishmentItem

    _require_role(user, sales=True)

    # 11-§1: konfiguratsiyadan tug'ilgan shartnomada bu eshik YOPIQ — nima
    # yetishmayotganini konfiguratsiya biladi (tarkib va `missing` o'sha
    # yerda), shartnoma tomonidagi hisob bronlardan chiqarilib boshqa raqam
    # berishi mumkin. Bu eshik to'g'ridan-to'g'ri ombordan sotuv uchun.
    if contract.configuration_id:
        raise ValidationError({
            'detail': (
                'Bu shartnoma konfiguratsiyadan tug\'ilgan — yetishmayotganni '
                'engineer konfiguratsiya sahifasidan yuboradi.'
            ),
        })

    # Zanjir bo'yicha bitta ochiq TLD (11-§1) — eshik bo'yicha emas
    from apps.configurator.services import chain_open_replenishment

    existing = chain_open_replenishment(contract=contract)
    if existing:
        raise ValidationError({
            'detail': (
                f'{contract.number} uchun {existing.number} hisobi allaqachon '
                f'ochilgan ({existing.get_status_display()}).'
            ),
            'replenishment': existing.pk,
        })

    warehouse = main_warehouse()
    missing = []
    for item in contract.items.select_related('product'):
        reserved = (
            StockReservation.objects.filter(
                contract=contract, product=item.product,
                status=StockReservation.Status.ACTIVE,
                kind=StockReservation.Kind.HARD,
            ).aggregate(t=Sum('quantity'))['t'] or 0
        )
        shortage = item.quantity - reserved
        if shortage > 0:
            missing.append((item.product, shortage))
    if not missing:
        raise ValidationError({
            'detail': 'Barcha mahsulot band qilingan — buyurtmachiga yuborish shart emas.',
        })

    replenishment = Replenishment.objects.create(
        warehouse=warehouse,
        contract=contract,
        owner_sales=contract.created_by,
        note=f'{contract.number} shartnomasi uchun yetishmayotgan mahsulotlar',
        created_by=user,
    )
    for product, quantity in missing:
        ReplenishmentItem.objects.create(
            replenishment=replenishment,
            product=product,
            quantity=quantity,
            unit_price=product.cost_price or 0,
            note=f'{contract.number} shartnomasi uchun',
        )

    names = ', '.join(product.name for product, _ in missing)
    messages = {
        User.Role.SUPPLIER: 'kirim qilish kerak — shartnoma shu kirimni kutadi.',
        User.Role.BUGALTER: 'tekshirib chiqing — buyurtmachi yuborgach tasdiq sizdan boshlanadi.',
    }
    for recipient in User.objects.filter(role__in=messages.keys(), is_active=True):
        Notification.objects.create(
            user=recipient,
            title=f"{contract.number}: omborda yo'q mahsulotlar ({replenishment.number})",
            message=f'{names} — {messages[recipient.role]}',
            level=Notification.Level.WARNING,
            entity='Replenishment',
            object_id=str(replenishment.pk),
        )
    return replenishment


# ---------------------------------------------------------------------------
# 21-§3: shartnoma matni — shablon + avtomatik bloklar. `.docx` yuklash,
# Collabora/OnlyOffice va WOPI **butunlay olib tashlandi** (17-to'plam va
# DOCX-QARORLAR.md o'rnini bosadi): sales shablon yozadi, shartnoma shu
# shablondan shakllanadi, o'rin egallovchilar (`{{ key }}`) KO'RSATISHDA
# to'ladi, rekvizit/spetsifikatsiya bloklarini esa tizimning o'zi quradi.
# ---------------------------------------------------------------------------

# Hujjat huquqiy — Didoxga ketgandan keyin (`pending_didox`) tahrir yopiladi
CONTRACT_DOCUMENT_EDITABLE_STATUSES = {
    Contract.Status.DRAFT, Contract.Status.REJECTED,
    Contract.Status.PENDING_BUGALTER, Contract.Status.PENDING_ADMIN,
    Contract.Status.READY_FOR_DIDOX,
}


def get_or_create_contract_document(contract):
    from apps.sales.models import ContractDocument

    document, _created = ContractDocument.objects.get_or_create(contract=contract)
    return document


def _require_document_editable(contract):
    if contract.status not in CONTRACT_DOCUMENT_EDITABLE_STATUSES:
        raise ValidationError({
            'detail': (
                'Hujjat matni endi tahrirlanmaydi — shartnoma Didoxga '
                'yuborilgan yoki imzolangan.'
            ),
        })


KNOWN_CONTRACT_PLACEHOLDER_KEYS = {
    'contract.number', 'contract.date', 'contract.city',
    'contract.total', 'contract.total_words',
    'contract.prepayment_percent', 'contract.prepayment_days',
    'contract.delivery_days',
    'company.name', 'company.director_name', 'company.director_title',
    'company.inn', 'company.address', 'company.bank_name', 'company.mfo',
    'company.account_number', 'company.oked', 'company.registration_code',
    'company.license',
    'client.name', 'client.director_name', 'client.director_title',
    'client.inn', 'client.address', 'client.bank_name', 'client.mfo',
    'client.account_number',
}

_PLACEHOLDER_RE = re.compile(r'\{\{\s*([\w.]+)\s*\}\}')

_RU_MONTHS = [
    'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
    'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря',
]
_UZ_MONTHS = [
    'yanvar', 'fevral', 'mart', 'aprel', 'may', 'iyun',
    'iyul', 'avgust', 'sentyabr', 'oktyabr', 'noyabr', 'dekabr',
]


def extract_placeholder_keys(body):
    """Matndagi barcha `{{ key }}` kalitlar (takrorsiz)."""
    return set(_PLACEHOLDER_RE.findall(body or ''))


def unknown_placeholder_keys(body):
    """21-§3.3: shablon saqlashda tekshiriladi — noma'lum kalit jimgina yo'qolmasin."""
    return sorted(extract_placeholder_keys(body) - KNOWN_CONTRACT_PLACEHOLDER_KEYS)


def _format_contract_date(date_obj, language):
    if date_obj is None:
        return ''
    if language == 'uz':
        return f'{date_obj.day} {_UZ_MONTHS[date_obj.month - 1]} {date_obj.year} yil'
    return f'{date_obj.day} {_RU_MONTHS[date_obj.month - 1]} {date_obj.year} г.'


def _contract_document_placeholders(contract):
    """21-§3.3(a): qiymat kalitlari — KO'RSATISHDA to'ldiriladi, bazada
    saqlanmaydi (summa o'zgarsa hujjat o'zi ergashadi, `is_stale` yo'q)."""
    from apps.core.models import CompanyProfile
    from apps.core.utils import amount_in_words

    company = CompanyProfile.load()
    client = contract.client
    document = getattr(contract, 'document', None)
    template = document.template if document and document.template_id else None
    language = template.language if template else 'ru'
    date_source = contract.signed_at or localdate()
    total = contract.items_total_with_vat

    return {
        'contract.number': contract.number,
        'contract.date': _format_contract_date(date_source, language),
        'contract.city': company.city,
        'contract.total': str(total),
        'contract.total_words': amount_in_words(total, language=language),
        'contract.prepayment_percent': str(contract.prepayment_percent or ''),
        # §3.4: alohida "necha kun ichida to'lansin" maydon yo'q — bron
        # muddati (`contract_reservation_days`) shu ma'noni eng yaqin beradi
        'contract.prepayment_days': str(company.contract_reservation_days),
        'contract.delivery_days': str(contract.delivery_days),
        'company.name': company.name,
        'company.director_name': company.director_name,
        'company.director_title': company.director_title,
        'company.inn': company.inn,
        'company.address': company.address,
        'company.bank_name': company.bank_name,
        'company.mfo': company.mfo,
        'company.account_number': company.account_number,
        'company.oked': company.oked,
        'company.registration_code': company.registration_code,
        'company.license': company.license,
        'client.name': client.display_name if client else '',
        'client.director_name': getattr(client, 'director_name', '') or '',
        'client.director_title': getattr(client, 'director_title', '') or '',
        'client.inn': getattr(client, 'inn', '') or '',
        'client.address': getattr(client, 'address', '') or '',
        'client.bank_name': getattr(client, 'bank_name', '') or '',
        'client.mfo': getattr(client, 'mfo', '') or '',
        'client.account_number': getattr(client, 'account_number', '') or '',
    }


def render_contract_document(contract, body):
    """O'rin egallovchilarni KO'RSATISHDA to'ldiradi — saqlashda emas.

    Shunda summa o'zgarsa (masalan partiya soni) hujjat ham ergashadi —
    21-§3.2: bazadagi `body`da `{{ }}` doim saqlanib turadi, "eskirdi"
    (`is_stale`) degan tushuncha shu sabab umuman yo'q.

    Hujjatning o'zi bugalter/admin/sales(egasi)dan boshqasiga umuman
    ochilmaydi (view darajasida), shuning uchun bu yerda qo'shimcha
    maskalash shart emas.
    """
    values = _contract_document_placeholders(contract)

    def repl(match):
        key = match.group(1).strip()
        return values.get(key, match.group(0))

    return _PLACEHOLDER_RE.sub(repl, body or '')


@atomic
def attach_contract_template(contract, template, user):
    """21-§3.6: sales shablon tanlaydi — matn BUTUNLAY almashadi.

    `template` FK faqat "qaysi shablondan kelgan" ma'lumoti: matnning o'zi
    shu yerda nusxalanadi, shablon keyin tahrirlansa yoki o'chirilsa ham
    ochiq shartnomaga ta'sir qilmaydi (`SET_NULL`, 21-§3.2/3.6).
    """
    _require_document_editable(contract)
    document = get_or_create_contract_document(contract)
    document.template = template
    document.body = template.body
    document.has_specification = template.has_specification
    document.has_requisites = template.has_requisites
    document.updated_by = user
    document.save()
    document.versions.create(body=document.body, created_by=user)
    return document


_QL_ALIGN_STYLES = {
    'ql-align-center': 'text-align: center',
    'ql-align-right': 'text-align: right',
    'ql-align-justify': 'text-align: justify',
}
_QL_TAG_RE = re.compile(r'<[a-zA-Z][a-zA-Z0-9]*\b[^>]*class="[^"]*"[^>]*>')


def _inline_legacy_styles(html):
    """21-§3.7: muharrir (Quill) ba'zi formatlarni CSS SINFI bilan yozadi
    (`class="ql-align-center"`), inline uslub bilan emas — PDF renderer va
    pochta mijozi muharrir CSS'ini yuklamaydi (Navigo saboqi). Shuning
    uchun saqlash chegarasida INLINE uslub ham qo'shiladi: sinf ham qoladi
    (muharrir o'zinikini o'qiyveradi), uslub ham yoziladi (qolgan hamma
    joy — jumladan WeasyPrint — to'g'ri chizadi).
    """
    def add_style(match):
        tag = match.group(0)
        class_match = re.search(r'class="([^"]*)"', tag)
        if not class_match:
            return tag
        styles = []
        for cls in class_match.group(1).split():
            if cls in _QL_ALIGN_STYLES:
                styles.append(_QL_ALIGN_STYLES[cls])
            elif cls.startswith('ql-indent-'):
                suffix = cls.rsplit('-', 1)[-1]
                if suffix.isdigit():
                    styles.append(f'margin-left: {int(suffix) * 3}em')
        if not styles:
            return tag
        style_str = '; '.join(styles)
        style_match = re.search(r'style="([^"]*)"', tag)
        if style_match:
            existing = style_match.group(1).rstrip(';')
            merged = f'{existing}; {style_str}' if existing else style_str
            return tag[:style_match.start(1)] + merged + tag[style_match.end(1):]
        if tag.rstrip().endswith('/>'):
            return tag[:-2].rstrip() + f' style="{style_str}" />'
        return tag[:-1] + f' style="{style_str}">'

    return _QL_TAG_RE.sub(add_style, html or '')


@atomic
def set_contract_document_body(contract, user, body):
    """21-§3.6: sales (egasi)/bugalter/admin hujjat matnini tahrirlaydi.

    `.docx` yuklash yo'li olib tashlandi — endi HTML to'g'ridan-to'g'ri
    saqlanadi, muharrir sinflari saqlash chegarasida inline uslubga
    ko'chiriladi (§3.7).
    """
    _require_document_editable(contract)
    document = get_or_create_contract_document(contract)
    document.body = _inline_legacy_styles(body)
    document.updated_by = user
    document.save()
    document.versions.create(body=document.body, created_by=user)
    return document


def _specification_rows_html(contract):
    rows = []
    for idx, item in enumerate(contract.items.select_related('product'), start=1):
        rows.append(
            f'<tr><td>{idx}</td><td>{item.product.name}</td>'
            f'<td>{item.product.unit}</td><td>{item.quantity}</td>'
            f'<td>{item.unit_price}</td><td>{item.total_with_vat}</td></tr>',
        )
    return ''.join(rows)


def specification_block_html(contract, language='ru'):
    """21-§3.3(b): Спецификация — jadval + ИТОГО + summa so'z bilan (ramka,
    blok kalit emas — sales shablonga yozmaydi, tizim quradi)."""
    from apps.core.utils import amount_in_words

    if not contract.items.exists():
        return ''
    total = contract.items_total_with_vat
    total_label = "JAMI" if language == 'uz' else 'ИТОГО'
    headers = (
        ('№', 'Nomi', "O'lch.", 'Soni', 'Narxi', 'Summa') if language == 'uz'
        else ('№', 'Наименование', 'Ед. изм.', 'Кол-во', 'Цена', 'Сумма')
    )
    head_row = ''.join(f'<th>{cell}</th>' for cell in headers)
    return (
        '<table class="specification">'
        f'<thead><tr>{head_row}</tr></thead>'
        f'<tbody>{_specification_rows_html(contract)}</tbody>'
        f'<tfoot><tr><td colspan="5">{total_label}</td><td>{total}</td></tr></tfoot>'
        '</table>'
        f'<p class="total-words">{amount_in_words(total, language=language)}</p>'
    )


def requisites_block_html(contract):
    """21-§3.3(b): 10-bo'lim — ikki tomon rekvizitlari.

    Mijoz turi bo'yicha shoxlanadi: jismoniy shaxsda passport/JSHSHIR,
    yuridik shaxsda INN/bank (§3.6 case — jismoniy shaxs mijoz).
    """
    from apps.core.models import CompanyProfile
    from apps.clients.models import Client

    company = CompanyProfile.load()
    client = contract.client
    company_html = (
        '<div class="requisites-party">'
        f'<p>{company.name}</p>'
        f'<p>ИНН: {company.inn}</p>'
        f'<p>{company.address}</p>'
        f'<p>Банк: {company.bank_name}, МФО: {company.mfo}</p>'
        f'<p>Р/с: {company.account_number}</p>'
        f'<p>ОКЭД: {company.oked}</p>'
        '</div>'
    )
    if client and client.type == Client.Type.LEGAL:
        client_html = (
            '<div class="requisites-party">'
            f'<p>{client.display_name}</p>'
            f'<p>ИНН: {client.inn}</p>'
            f'<p>{client.address}</p>'
            f'<p>Банк: {client.bank_name}, МФО: {client.mfo}</p>'
            f'<p>Р/с: {client.account_number}</p>'
            '</div>'
        )
    else:
        client_html = (
            '<div class="requisites-party">'
            f'<p>{client.display_name if client else ""}</p>'
            f'<p>Паспорт: {getattr(client, "passport", "") or ""}</p>'
            f'<p>ПИНФЛ: {getattr(client, "jshshir", "") or ""}</p>'
            f'<p>{getattr(client, "address", "") or ""}</p>'
            '</div>'
        )
    return f'<div class="requisites">{company_html}{client_html}</div>'


def signature_block_html(contract):
    """21-§3.3(b): imzo bloklari (lavozim, F.I.SH, М.П.)."""
    from apps.core.models import CompanyProfile
    from apps.clients.models import Client

    company = CompanyProfile.load()
    client = contract.client
    is_legal = bool(client and client.type == Client.Type.LEGAL)
    client_title = client.director_title if is_legal else ''
    client_signer = client.director_name if is_legal and client.director_name else (
        client.display_name if client else ''
    )
    return (
        '<div class="signatures">'
        '<div class="signatures-party">'
        f'<p>{company.director_title or "Директор"}</p>'
        f'<p>____________ {company.director_name}</p><p>М.П.</p>'
        '</div>'
        '<div class="signatures-party">'
        f'<p>{client_title}</p>'
        f'<p>____________ {client_signer}</p><p>М.П.</p>'
        '</div>'
        '</div>'
    )


_CONTRACT_PDF_CSS = """
@page { size: A4; margin: 8mm }
body { font-family: DejaVu Sans, sans-serif; font-size: 11pt; }
.terms-content .ql-align-center { text-align: center; }
.terms-content .ql-align-right { text-align: right; }
.terms-content .ql-align-justify { text-align: justify; }
.terms-content .ql-indent-1 { margin-left: 3em; }
.terms-content .ql-indent-2 { margin-left: 6em; }
.terms-content .ql-indent-3 { margin-left: 9em; }
.terms-content .ql-indent-4 { margin-left: 12em; }
.terms-content .ql-indent-5 { margin-left: 15em; }
.terms-content .ql-indent-6 { margin-left: 18em; }
.terms-content .ql-indent-7 { margin-left: 21em; }
.terms-content .ql-indent-8 { margin-left: 24em; }
table.specification { width: 100%; border-collapse: collapse; margin-top: 1em; }
table.specification td, table.specification th { border: 1px solid #333; padding: 4px; }
.requisites, .signatures { display: flex; justify-content: space-between; margin-top: 2em; }
"""


def render_contract_pdf_html(contract):
    """21-§3.7: ramka HTML — WeasyPrint shu HTML'ni A4 PDF'ga chiqaradi.

    Ramka: sarlavha/muqaddima → sales matni (1-9 bo'lim) → rekvizit/imzo →
    spetsifikatsiya (§3.3b). Ramka CSS'ida muharrir sinflari qayta e'lon
    qilinadi — ikkinchi himoya, saqlashdagi inline uslub (§3.7) yetarli
    bo'lmagan eski yozuvlar uchun ham ishlaydi.
    """
    from apps.core.models import CompanyProfile
    from apps.clients.models import Client

    document = get_or_create_contract_document(contract)
    template = document.template
    language = template.language if template else 'ru'
    body_html = render_contract_document(contract, document.body)
    values = _contract_document_placeholders(contract)
    company = CompanyProfile.load()
    client = contract.client

    title = (
        f'{contract.number}-SON YETKAZIB BERISH SHARTNOMASI' if language == 'uz'
        else f'ДОГОВОР ПОСТАВКИ № {contract.number}'
    )
    company_role = 'Ijrochi' if language == 'uz' else 'Исполнитель'
    client_role = 'Mijoz' if language == 'uz' else 'Заказчик'
    is_legal = bool(client and client.type == Client.Type.LEGAL)
    preamble = (
        f'<p>«{company.name}», bundan buyon "{company_role}" '
        f'({company.director_title} {company.director_name} shaxsida), va '
        f'«{client.display_name if client else ""}», bundan buyon "{client_role}"'
        f'{f" ({client.director_title} {client.director_name} shaxsida)" if is_legal else ""}, '
        'quyidagi shartnomani tuzdilar:</p>'
        if language == 'uz' else
        f'<p>«{company.name}», именуемое в дальнейшем "{company_role}", '
        f'в лице {company.director_title} {company.director_name}, и '
        f'«{client.display_name if client else ""}», именуемое в дальнейшем "{client_role}"'
        f'{f", в лице {client.director_title} {client.director_name}" if is_legal else ""}, '
        'заключили настоящий договор:</p>'
    )

    blocks = [
        f'<h1>{title}</h1>',
        f'<p class="city-date">{values["contract.city"]} · {values["contract.date"]}</p>',
        f'<div class="preamble">{preamble}</div>',
        f'<div class="terms-content">{body_html}</div>',
    ]
    if document.has_requisites:
        blocks.append(requisites_block_html(contract))
        blocks.append(signature_block_html(contract))
    if document.has_specification:
        blocks.append(specification_block_html(contract, language))

    return (
        '<html><head><meta charset="utf-8">'
        f'<style>{_CONTRACT_PDF_CSS}</style></head>'
        f'<body>{"".join(blocks)}</body></html>'
    )


def render_contract_pdf(contract):
    """`GET /contracts/{id}/document/export/?format=pdf` — A4 PDF baytlari.

    Hujjat kichik — sinxron chiziladi (Navigo ham shunday qiladi).
    """
    from weasyprint import HTML

    return HTML(string=render_contract_pdf_html(contract)).write_pdf()


# ---------------------------------------------------------------------------
# 21-§3.5: shartnoma raqami — `NB2309-26`. Yangi shartnomalarga; eski
# `SHT-000xx` yozuvlar o'zgarmaydi (raqam faqat bo'sh bo'lganda hisoblanadi).
# ---------------------------------------------------------------------------

_CYRILLIC_TO_LATIN_INITIAL = {
    'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'E',
    'Ж': 'J', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
    'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
    'Ф': 'F', 'Х': 'X', 'Ц': 'S', 'Ч': 'C', 'Ш': 'S', 'Щ': 'S', 'Ъ': '',
    'Ы': 'I', 'Ь': '', 'Э': 'E', 'Ю': 'Y', 'Я': 'Y', 'Ў': 'O', 'Қ': 'Q',
    'Ғ': 'G', 'Ҳ': 'H',
}


def _transliterate_initial(letter):
    upper = (letter or '').upper()
    return _CYRILLIC_TO_LATIN_INITIAL.get(upper, upper)


def _contract_owner_initials(user):
    """21-§3.5: ism/familiyadan ikki harf, Kirill bo'lsa transliteratsiya bilan.

    To'liq ism yo'q (faqat `username`) — uning birinchi ikki harfi. Bitta
    so'zli ism ham xuddi shu qoida bilan (aniq va bashorat qilsa bo'ladigan
    bo'lishi uchun — ikkinchi harf yo'qligidan chalkashib yurmaslik uchun).
    """
    if user is None:
        return 'XX'
    first = (user.first_name or '').strip()
    last = (user.last_name or '').strip()
    if first and last:
        return _transliterate_initial(first[0]) + _transliterate_initial(last[0])
    single_word = first or last
    if not single_word:
        single_word = (user.username or '').strip()
    if len(single_word) >= 2:
        return (
            _transliterate_initial(single_word[0]) + _transliterate_initial(single_word[1])
        ).upper()
    if single_word:
        return (_transliterate_initial(single_word[0]) * 2).upper()
    return 'XX'


def contract_number(user, when=None):
    """21-§3.5: `NB2309-26` — sales bosh harflari + kun/oy + yil.

    Egasi — shartnomani ochgan sales (avtomatik ochilganda: zayavkani
    yozgan sales, `create_contract_from_configuration`dagi `owner`),
    tugmani bosgan odam emas.
    """
    when = when or localdate()
    return f'{_contract_owner_initials(user)}{when.day:02d}{when.month:02d}-{when:%y}'


def unique_contract_number(candidate):
    """Takror — bitta sales bir kunda ikkita shartnoma ochsa: `/2`, `/3` …"""
    from apps.sales.models import Contract as _Contract

    if not _Contract.objects.filter(number=candidate).exists():
        return candidate
    suffix = 2
    while _Contract.objects.filter(number=f'{candidate}/{suffix}').exists():
        suffix += 1
    return f'{candidate}/{suffix}'
