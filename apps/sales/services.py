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
    """Yakunlangan konfiguratsiyadan avtomatik draft shartnoma ochadi.

    Sales finalize qilganda chaqiriladi — bugalterga yuborishdan oldin
    shartnoma (chop etish shakli bilan) tayyor turadi. Mijoz: berilgan
    `client`, bo'lmasa zayavkadagi (ZVK) mijoz. Mijoz aniqlanmasa shartnoma
    ochilmaydi (None qaytadi) — sales qo'lda ochishi mumkin.

    Qator: tayyor variant (yo'q bo'lsa bazaviy model), narxi konfiguratsiya
    narxidan (QQS'siz), QQS esa default foiz bilan qo'shiladi.
    """
    existing = Contract.objects.filter(configuration=configuration).first()
    if existing:
        return existing

    request_obj = (
        configuration.requests.filter(created_by__isnull=False)
        .order_by('-created_at').first()
    )
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

    # §11.4: konfiguratsiyaning yumshoq broni shartnomaning qattiq broniga
    # aylanadi — endi bu mol sotilgan hisoblanadi
    from apps.inventory.services import sync_contract_reservations

    sync_contract_reservations(contract)

    # §10.8: zanjir yopilib boradi — kelishuv shartnomaga bog'lanadi,
    # bajarilgan zayavka arxivga o'tadi (sales navbatini band qilmaydi)
    link_lead_to_contract(contract)
    from apps.configurator.models import ConfigurationRequest

    configuration.requests.filter(
        status=ConfigurationRequest.Status.DONE,
    ).update(status=ConfigurationRequest.Status.ARCHIVED)
    return contract


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

    paid_at = paid_at or now()
    first_payment = contract.status == Contract.Status.APPROVED
    if is_prepayment is None:
        is_prepayment = first_payment

    if first_payment:
        # §10.1: konfiguratsiyadan kelgan variant hali yig'ilmagan bo'lsa,
        # to'lov oldidan yig'ib olinadi (butlovchilar chiqib, variant kiradi) —
        # yetmasa quyidagi ship tekshiruvi aniq nomlar bilan 400 beradi
        if contract.configuration_id:
            from apps.configurator.services import assemble_variant

            assemble_variant(contract.configuration, user, strict=False)
        _ship_contract_items(contract, user)
        # §11.4: bron chiqimga aylandi
        from apps.inventory.services import mark_reservations_shipped

        mark_reservations_shipped(contract)

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
    if contract.balance <= 0:
        contract.status = Contract.Status.COMPLETED
    contract.save()
    return payment
