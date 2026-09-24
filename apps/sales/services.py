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

    shortages = [
        f'{item.product.name} (kerak: {item.quantity}, '
        f'sotuvga ochiq: {_open(item.product)})'
        for item in contract.items.select_related('product')
        if _open(item.product) < item.quantity
    ]
    if shortages:
        raise ValidationError({
            'detail': 'Omborda sotish uchun mahsulot yetarli emas.',
            'items': shortages,
        })

    for item in contract.items.select_related('product'):
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
# 13-§1/15-§A: shartnoma matni — bugalter `.docx` yuklaydi (yoki Collabora'da
# tahrirlaydi), sayt faqat KO'RSATADI. QOLGAN-ISHLAR-2 §4: to'g'ridan-to'g'ri
# HTML tahrir (`PUT`) olib tashlandi — Didoxga `source_file` ketadi, `body`ni
# alohida saqlash ikkinchi (eski) manba yaratardi.
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


def _contract_document_docxtpl_context(contract):
    """15-§A: `.docx` shablon uchun — dot-notation ishlashi uchun ICHMA-ICH lug'at.

    QOLGAN-ISHLAR-2 §1: `items` — shartnoma bandlari, Word jadvalida
    `{%tr for item in items %}...{%tr endfor %}` sikli bilan chiqariladi
    (docxtpl subdoc sintaksisi). `items_total`/`vat_total` — `total`
    (QQS bilan) yonida QQS'siz jami va QQS summasi alohida.
    """
    client = contract.client
    return {
        'contract': {
            'number': contract.number,
            'date': contract.signed_at.strftime('%d.%m.%Y') if contract.signed_at else '',
        },
        'client': {
            'name': client.display_name if client else '',
            'inn': getattr(client, 'inn', '') or '',
        },
        'items': [
            {
                'name': item.product.name,
                'sku': item.product.sku,
                'quantity': item.quantity,
                'unit_price': str(item.unit_price),
                'vat_percent': str(item.vat_percent),
                'total': str(item.total_with_vat),
            }
            for item in contract.items.select_related('product')
        ],
        'items_total': str(contract.items_total),
        'vat_total': str(contract.vat_total),
        'total': str(contract.items_total_with_vat),
        'prepayment_percent': str(contract.prepayment_percent or ''),
        'term_days': str(contract.term_days),
    }


def fill_contract_document_template(contract, file):
    """15-§A: shablondagi `{{ }}` o'rin egallovchilarni STATIK to'ldiradi.

    Fayl Didoxga aynan shu holicha ketadi (Collabora'da tahrirlanadi),
    shuning uchun avtomatik yangilanish endi yo'q — summa o'zgarsa
    bugalter qayta yuklaydi. Shablonda tag bo'lmasa (oddiy .docx) —
    docxtpl hech narsani o'zgartirmay saqlaydi, xato bermaydi.
    """
    from io import BytesIO

    from docxtpl import DocxTemplate

    template = DocxTemplate(file)
    try:
        template.render(_contract_document_docxtpl_context(contract))
    except Exception as exc:
        raise ValidationError({
            'file': f"Shablondagi o'rin egallovchida xatolik: {exc}",
        })
    buffer = BytesIO()
    template.save(buffer)
    return buffer.getvalue()


@atomic
def upload_contract_document(contract, user, file):
    """`.docx` yuklash (13-§1 bosqich 3, 15-§A bilan yangilangan).

    15-§A: fayl endi Didoxga AYNAN shu holicha ketadi (piksel-piksel) —
    shuning uchun `mammoth`ning "toza HTML"si energa faqat KO'RISH uchun
    (o'qish rejimi), tahrir Collabora Online orqali `source_file`ning
    o'zida bo'ladi (`edit_contract_document_session`). O'rin
    egallovchilar shu yerda, yuklashda, statik to'ldiriladi (`docxtpl`).
    """
    _require_document_editable(contract)
    name = (getattr(file, 'name', '') or '').lower()
    if not name.endswith('.docx'):
        raise ValidationError({
            'file': 'Matnga o\'girish faqat .docx uchun ishlaydi — .doc/boshqa formatlar hali qo\'llab-quvvatlanmaydi.',
        })
    filled = fill_contract_document_template(contract, file)
    preview = _mammoth_html(filled)

    document = get_or_create_contract_document(contract)
    document.body = preview
    _save_document_file(document, getattr(file, 'name', 'shartnoma.docx'), filled)
    document.source_uploaded_at = now()
    document.rendered_total = contract.total_amount
    document.docx_version += 1
    document.updated_by = user
    document.save()
    document.versions.create(body=document.body, created_by=user)
    return document


def _mammoth_html(docx_bytes):
    from io import BytesIO

    import mammoth

    return mammoth.convert_to_html(BytesIO(docx_bytes)).value


def _save_document_file(document, name, content_bytes):
    from django.core.files.base import ContentFile

    document.source_file.save(name, ContentFile(content_bytes), save=False)


# ---------------------------------------------------------------------------
# 15-§A: Collabora Online (WOPI) — `.docx` brauzerda to'g'ridan-to'g'ri
# tahrirlanadi, Didoxga AYNAN shu fayl ketadi (piksel-piksel bir xil).
# ---------------------------------------------------------------------------

_WOPI_SIGNER_SALT = 'contract-document-wopi'


def create_wopi_token(document, user):
    """Collabora `access_token=` sifatida yuboradigan, muddatli imzolangan token."""
    from django.core.signing import TimestampSigner

    return TimestampSigner(salt=_WOPI_SIGNER_SALT).sign(f'{document.pk}:{user.pk}')


def verify_wopi_token(token):
    """Tokenni tekshiradi — muddati o'tgan/soxta bo'lsa `(None, None)`."""
    from django.conf import settings
    from django.core.signing import BadSignature, SignatureExpired, TimestampSigner

    from apps.accounts.models import User
    from apps.sales.models import ContractDocument

    signer = TimestampSigner(salt=_WOPI_SIGNER_SALT)
    try:
        raw = signer.unsign(token or '', max_age=settings.WOPI_TOKEN_TTL_MINUTES * 60)
    except (BadSignature, SignatureExpired):
        return None, None
    try:
        document_id, user_id = raw.split(':')
        document = ContractDocument.objects.select_related('contract').get(pk=document_id)
        user = User.objects.get(pk=user_id)
    except (ValueError, ContractDocument.DoesNotExist, User.DoesNotExist):
        return None, None
    return document, user


def edit_contract_document_session(contract, user):
    """`POST /contracts/{id}/document/edit-session/` — Collabora iframe manzili.

    Faqat `.docx` allaqachon yuklangan bo'lsa (Collabora bo'sh hujjatni
    bilmaydi — shablon avval `document/upload/` orqali keladi).
    """
    from urllib.parse import urlencode

    from django.conf import settings

    _require_document_editable(contract)
    document = get_or_create_contract_document(contract)
    if not document.source_file:
        raise ValidationError({
            'detail': "Avval .docx shablon yuklansin (document/upload/) — tahrir shundan keyin ochiladi.",
        })
    token = create_wopi_token(document, user)
    wopi_src = f'{settings.WOPI_PUBLIC_URL}/api/wopi/files/{document.pk}'
    query = urlencode({'WOPISrc': wopi_src, 'access_token': token})
    return {
        'edit_url': f'{settings.COLLABORA_URL}/browser/dist/cool.html?{query}',
        'wopi_src': wopi_src,
    }


def wopi_check_file_info(document, user):
    """WOPI `CheckFileInfo` — Collabora tahrirni ochishdan oldin so'raydi."""
    return {
        'BaseFileName': _wopi_file_name(document),
        'Size': document.source_file.size if document.source_file else 0,
        'OwnerId': str(document.updated_by_id or 'system'),
        'UserId': str(user.pk),
        'UserFriendlyName': user.display_name,
        'Version': str(document.docx_version),
        'UserCanWrite': True,
        'SupportsLocks': True,
        'SupportsUpdate': True,
    }


def _wopi_file_name(document):
    if document.source_file:
        return document.source_file.name.rsplit('/', 1)[-1]
    return f'{document.contract.number}.docx'


def wopi_get_file_content(document):
    """WOPI `GetFile` — Collabora tahrir boshida faylni shu yerdan o'qiydi."""
    document.source_file.open('rb')
    try:
        return document.source_file.read()
    finally:
        document.source_file.close()


def _wopi_lock_expiry():
    from datetime import timedelta

    from django.conf import settings

    return now() + timedelta(minutes=settings.WOPI_LOCK_TTL_MINUTES)


@atomic
def wopi_lock_file(document, lock_id):
    """WOPI `LOCK` — boshqa sessiya qulfini egallab turgan bo'lsa `False`."""
    if document.wopi_lock_active and document.wopi_lock != lock_id:
        return False
    document.wopi_lock = lock_id
    document.wopi_lock_expires_at = _wopi_lock_expiry()
    document.save(update_fields=['wopi_lock', 'wopi_lock_expires_at'])
    return True


@atomic
def wopi_unlock_file(document, lock_id):
    """WOPI `UNLOCK` — boshqa qulf bo'lsa `False` (Collabora 409 qaytaradi)."""
    if document.wopi_lock_active and document.wopi_lock != lock_id:
        return False
    document.wopi_lock = ''
    document.wopi_lock_expires_at = None
    document.save(update_fields=['wopi_lock', 'wopi_lock_expires_at'])
    return True


def wopi_refresh_lock(document, lock_id):
    """WOPI `REFRESH_LOCK` — muddatni uzaytiradi, qulf o'zi bilan bir xil."""
    return wopi_lock_file(document, lock_id)


@atomic
def wopi_put_file(document, user, content, lock_id):
    """WOPI `PutFile` — Collabora tahrirlangan faylni shu yerga saqlaydi.

    15-§A: bu — asl (Didoxga ketadigan) fayl, qulf mos kelmasa rad
    etiladi (`False` — chaqiruvchi 409 qaytaradi). `body` ham qayta
    o'giriladi — saytdagi ko'rish rejimi Collabora'dan chiqqan versiyaga
    ergashsin.
    """
    if document.wopi_lock_active and document.wopi_lock != lock_id:
        return False
    _save_document_file(document, _wopi_file_name(document), content)
    document.body = _mammoth_html(content)
    document.docx_version += 1
    document.source_uploaded_at = now()
    document.updated_by = user
    document.save()
    document.versions.create(body=document.body, created_by=user)
    return True


def _contract_document_placeholders(contract):
    """13-§1: avtomatik maydonlar — bugalter qo'lda yozmasin, summa ergashsin."""
    client = contract.client
    rows = ''.join(
        f'<tr><td>{item.product.name}</td><td>{item.quantity}</td></tr>'
        for item in contract.items.select_related('product')
    )
    return {
        'contract.number': contract.number,
        'contract.date': contract.signed_at.strftime('%d.%m.%Y') if contract.signed_at else '',
        'client.name': client.display_name if client else '',
        'client.inn': getattr(client, 'inn', '') or '',
        'items_table': f'<table>{rows}</table>',
        'total': str(contract.items_total_with_vat),
        'prepayment_percent': str(contract.prepayment_percent or ''),
        'term_days': str(contract.term_days),
    }


def render_contract_document(contract, body):
    """O'rin egallovchilarni KO'RSATISHDA to'ldiradi — saqlashda emas.

    Shunda summa o'zgarsa (masalan partiya soni) hujjat ham ergashadi.

    QOLGAN-ISHLAR #3: `total`/`prepayment_percent` — shartnomaning JAMI
    summasi, `PRICE_FIELDS` qoidasi bunga tegishli emas (u faqat QATOR
    narxini — `unit_price` va h.k. — sales/adminga cheklaydi). Jami
    summani bugalter ham allaqachon shartnoma kartasida ko'radi, hujjatda
    yashirish esa uni yozayotgan odamdan asosiy raqamni olib qo'yardi.
    Hujjatning o'zi bugalter/admin/sales(egasi)dan boshqasiga umuman
    ochilmaydi (view darajasida), shuning uchun bu yerda qo'shimcha
    maskalash shart emas.
    """
    import re

    values = _contract_document_placeholders(contract)

    def repl(match):
        key = match.group(1).strip()
        return values.get(key, match.group(0))

    return re.sub(r'\{\{\s*([\w.]+)\s*\}\}', repl, body or '')
