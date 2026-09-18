from decimal import Decimal

from django.db.models import Sum
from django.db.transaction import atomic
from django.utils.timezone import localdate, now
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.core.models import Notification
from apps.finance.services import record_transaction
from apps.sales.models import Contract, ContractApproval, ContractItem, ContractPayment, Lead


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

    Zanjir 18-qadamda tugaydi; ungacha ZVK ro'yxatlarda ko'rinib, roadmap
    umurtqasi bo'lib turadi.
    """
    from apps.configurator.models import ConfigurationRequest

    if contract.status != Contract.Status.COMPLETED or not contract.configuration_id:
        return
    contract.configuration.requests.filter(
        status=ConfigurationRequest.Status.DONE,
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
def approve_contract(contract, user, comment='', didox_number=''):
    """Bugalter (Didox qabuli) -> admin zanjiri bo'yicha tasdiqlash.

    §11.2: bugalter bosqichi — "Didoxdan qabul qildim va tanishdim":
    `didox_number` shu yerda saqlanadi. §11.3: summa chegaradan kichik bo'lsa
    admin bosqichi o'tkazib yuboriladi (tarixda avtomatik yozuv qoladi).
    """
    admin_skipped = False
    if contract.status == Contract.Status.PENDING_BUGALTER:
        _require_role(user, bugalter=True)
        step = ContractApproval.Step.BUGALTER
        if didox_number:
            contract.didox_number = didox_number
            contract.didox_accepted_at = now()
        # Chop etish shaklida sana bo'sh qolmasin — qabul kuni imzo sanasi
        if not contract.signed_at:
            contract.signed_at = localdate()
        admin_skipped = _admin_threshold_skip(contract)
        contract.status = (
            Contract.Status.APPROVED if admin_skipped
            else Contract.Status.PENDING_ADMIN
        )
    elif contract.status == Contract.Status.PENDING_ADMIN:
        _require_role(user, admin=True)
        step = ContractApproval.Step.ADMIN
        contract.status = Contract.Status.APPROVED
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
        # Tarix jim qolmasin: nega admin ko'rmagani yozib qo'yiladi
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
    elif contract.status == Contract.Status.APPROVED:
        if admin_skipped:
            pay_message = (
                f"Summa chegaradan past — admin tasdig'i talab qilinmadi. "
                f"Oldindan to'lov {contract.prepayment_percent}% — "
                f'{contract.prepayment_amount} {contract.currency}. '
                'Pul kelgach confirm-payment qiling.'
            )
            creator_message = (
                'Bugalter tasdiqladi (summa chegaradan past — admin shart emas) '
                '— mijozdan to\'lov kutilmoqda.'
            )
            title = f'{contract.number}: tasdiqlandi — pul kutilmoqda'
        else:
            pay_message = (
                f"Oldindan to'lov {contract.prepayment_percent}% — "
                f'{contract.prepayment_amount} {contract.currency}. '
                'Pul kelgach confirm-payment qiling.'
            )
            creator_message = 'Bugalter va admin tasdiqladi — mijozdan to\'lov kutilmoqda.'
            title = f'{contract.number}: admin tasdiqladi — pul kutilmoqda'
        _notify_role(User.Role.BUGALTER, contract, title=title, message=pay_message)
        if contract.created_by:
            Notification.objects.create(
                user=contract.created_by,
                title=f'{contract.number}: shartnoma tasdiqlandi',
                message=creator_message,
                level=Notification.Level.INFO,
                entity='Contract',
                object_id=str(contract.pk),
            )
    return contract


@atomic
def reject_contract(contract, user, comment=''):
    """Bugalter yoki admin shartnomani rad etadi."""
    if contract.status == Contract.Status.PENDING_BUGALTER:
        _require_role(user, bugalter=True)
        step = ContractApproval.Step.BUGALTER
    elif contract.status == Contract.Status.PENDING_ADMIN:
        _require_role(user, admin=True)
        step = ContractApproval.Step.ADMIN
    else:
        raise ValidationError('Shartnoma tasdiqlash bosqichida emas.')

    contract.status = Contract.Status.REJECTED
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
    )
    if contract.created_by:
        Notification.objects.create(
            user=contract.created_by,
            title=f'{contract.number}: shartnoma qaytarildi',
            message=comment,
            level=Notification.Level.WARNING,
            entity='Contract',
            object_id=str(contract.pk),
        )
    # §11.4: rad etilgan shartnoma molni ushlab turmaydi — bron bo'shaydi
    # (sales tuzatib qayta yuborsa, submit'da qayta band qilinadi)
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

    # §11.4 eng nozik joy: erkin qoldiq + SHU shartnomaning o'z broni —
    # aks holda shartnoma o'zi band qilgan molga o'zi yetisha olmay qolardi
    shortages = [
        f'{item.product.name} (kerak: {item.quantity}, '
        f'sotuvga ochiq: {sellable_quantity(item.product, warehouse, for_contract=contract)})'
        for item in contract.items.select_related('product')
        if sellable_quantity(item.product, warehouse, for_contract=contract) < item.quantity
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


@atomic
def ship_contract(contract, user):
    """Yetkazib berish (#2): mol AYNAN shu yerda ombordan chiqadi.

    Kim: buyurtmachi yoki bugalter (admin) — mol bilan ishlaydigan odam.
    Shartlari: boshlang'ich to'lov qabul qilingan (`active`), hali
    yetkazilmagan, mol yetarli (o'z broni o'ziga ochiq). Bir marta, to'liq —
    qisman yetkazish hozircha yo'q. Balans yopiq bo'lsa shu yerda `completed`.
    """
    if not user or not user.is_authenticated:
        raise PermissionDenied('Avtorizatsiya talab qilinadi.')
    if not (user.is_admin or user.is_supplier or user.is_bugalter):
        raise PermissionDenied('Yetkazishni buyurtmachi yoki bugalter belgilaydi.')
    if contract.delivered_at:
        raise ValidationError({'detail': 'Bu shartnoma allaqachon yetkazilgan.'})
    if contract.status not in {Contract.Status.ACTIVE, Contract.Status.COMPLETED}:
        raise ValidationError({
            'detail': "Avval boshlang'ich to'lov qabul qilinsin — yetkazish faol shartnomada.",
        })

    _ship_contract_items(contract, user)
    # §11.4: bron chiqimga aylandi
    from apps.inventory.services import mark_reservations_shipped

    mark_reservations_shipped(contract)

    contract.delivered_at = localdate()
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

    existing = next(
        (rep for rep in contract.replenishments.all() if rep.is_open), None,
    )
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
