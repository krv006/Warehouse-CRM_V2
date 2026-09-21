from decimal import Decimal

from django.db.transaction import atomic
from django.utils.timezone import localdate, now
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.core.models import Notification
from apps.finance.models import Loan
from apps.finance.services import cash_balance, record_transaction
from apps.inventory.models import Product, StockMovement
from apps.inventory.services import apply_movement
from apps.procurement.models import (
    DEBT_TERM_DAYS,
    Replenishment,
    ReplenishmentApproval,
    ReplenishmentEvent,
    ReplenishmentItem,
)


def _require(user, *, supplier=False, bugalter=False, sales=False, admin=False):
    if not user or not user.is_authenticated:
        raise PermissionDenied('Avtorizatsiya talab qilinadi.')
    if user.is_admin:
        return
    if supplier and user.is_supplier:
        return
    if bugalter and user.is_bugalter:
        return
    if sales and user.is_sales:
        return
    if admin:
        raise PermissionDenied('Bu bosqichni faqat admin tasdiqlaydi.')
    raise PermissionDenied('Bu amal uchun ruxsat yo\'q.')


def low_stock_queryset(warehouse=None):
    """Yetishmayotganlar — TO'LIQ SQL darajasida (EGALIK §2.4 unumdorlik).

    Hisoblagich har daqiqada chaqiriladi, shuning uchun bu yerda Python
    sikli emas, bitta annotatsiyali so'rov: erkin qoldiq (jami − qattiq
    bron, §11.4: band mol sotilgan hisoblanadi) <= reorder_level.
    Har bir qatorga `current_stock` annotatsiyasi biriktiriladi.
    """
    from django.db.models import DecimalField, F, OuterRef, Subquery, Sum, Value
    from django.db.models.functions import Coalesce

    from apps.inventory.models import Stock, StockReservation

    stock_rows = Stock.objects.filter(product=OuterRef('pk'))
    reserved_rows = StockReservation.objects.filter(
        product=OuterRef('pk'),
        status=StockReservation.Status.ACTIVE,
        kind=StockReservation.Kind.HARD,
    )
    if warehouse is not None:
        stock_rows = stock_rows.filter(warehouse=warehouse)
        reserved_rows = reserved_rows.filter(warehouse=warehouse)

    zero = Value(0, output_field=DecimalField(max_digits=18, decimal_places=2))
    stock_sum = stock_rows.values('product').annotate(t=Sum('quantity')).values('t')
    reserved_sum = reserved_rows.values('product').annotate(t=Sum('quantity')).values('t')

    return (
        Product.objects.filter(is_active=True)
        .annotate(
            stock_quantity=Coalesce(Subquery(stock_sum), zero),
            hard_reserved=Coalesce(Subquery(reserved_sum), zero),
            current_stock=F('stock_quantity') - F('hard_reserved'),
        )
        .filter(current_stock__lte=F('reorder_level'))
    )


def low_stock_products(warehouse=None):
    """Qoldig'i tugagan yoki reorder darajasidan pastga tushgan mahsulotlar (TZ 7.1).

    Omborda hali umuman yozuvi yo'q mahsulot ham ro'yxatga tushadi — qoldig'i 0.
    """
    return list(low_stock_queryset(warehouse))


@atomic
def build_from_low_stock(warehouse, user, supplier=''):
    """Yetishmayotgan mahsulotlar ro'yxatidan to'ldirish buyurtmasini shakllantiradi."""
    _require(user, supplier=True)
    products = low_stock_products(warehouse)
    if not products:
        raise ValidationError('Omborda yetishmayotgan mahsulot topilmadi.')

    replenishment = Replenishment.objects.create(
        warehouse=warehouse,
        supplier=supplier,
        created_by=user,
    )
    for product in products:
        needed = max(product.reorder_level - product.current_stock, 1)
        ReplenishmentItem.objects.create(
            replenishment=replenishment,
            product=product,
            quantity=needed,
            unit_price=product.cost_price,
        )
    return replenishment


@atomic
def submit(replenishment, user):
    """Buyurtmachi hisobni tekshiruvga yuboradi — to'g'ridan-to'g'ri bugalterga.

    10-to'plam §4: eski oqimda shartnoma zanjir OXIRIDA tuzilardi va xarid
    narxi mijoz narxiga ta'sir qilardi — shuning uchun TLD avval sales'ga
    (mijoz roziligiga) borardi. Yangi oqimda TLD ochilishining o'zi
    "hammasi bo'lgan" degani: yechim tasdiqlangan, shartnoma Didoxdan
    o'tgan, BOSHLANG'ICH TO'LOV KELGAN. TLD raqamlari — bizning xarid
    tannarximiz; xarid qimmat chiqsa bu marja masalasi (bugalter/admin
    chegara qoidasi), mijozdan so'raydigan narsa yo'q. `PENDING_SALES`
    holati va approve/reject shoxi jonli bazadagi eski hisoblar uchun
    saqlab qolingan — faqat YANGI hisob u yerga tushmaydi.
    """
    _require(user, supplier=True)
    if replenishment.status not in {Replenishment.Status.DRAFT, Replenishment.Status.REJECTED}:
        raise ValidationError('Faqat qoralama holatidagi hisob yuboriladi.')
    if not replenishment.items.exists():
        raise ValidationError('Hisobda birorta ham mahsulot yo\'q.')

    no_price = [item for item in replenishment.items.all() if item.needs_price]
    if no_price:
        raise ValidationError({
            'items': [item.product.name for item in no_price],
            'detail': 'Narxi kiritilmagan pozitsiyalar bor.',
        })

    from apps.accounts.models import User

    replenishment.status = Replenishment.Status.PENDING_BUGALTER
    _notify_role(
        User.Role.BUGALTER, replenishment,
        title=f'{replenishment.number}: yangi hisob tekshiruvda',
        message=(
            'Buyurtmachi hisobni yubordi — tekshirib tasdiqlang, '
            'keyin adminga o\'tadi.'
        ),
    )
    # Sales VAZIFA emas, XABAR oladi: uning zanjiridan pul chiqmoqda va
    # muddat cho'zilishi mumkin — buni bilishi kerak (10-§4.2)
    if replenishment.owner_sales_id:
        source = replenishment.configuration or replenishment.contract
        Notification.objects.create(
            user=replenishment.owner_sales,
            title=f'{replenishment.number}: ta\'minot hisobi yuborildi',
            message=(
                f'{source.number if source else replenishment.number} '
                'zanjiringiz bo\'yicha TLD bugalterga yuborildi — muddat '
                'cho\'zilishi mumkin.'
            ),
            level=Notification.Level.INFO,
            entity='Replenishment',
            object_id=str(replenishment.pk),
        )
    replenishment.save()
    return replenishment


def _notify_role(role, replenishment, title, message):
    """Bosqich egasiga (roldagi barcha faol foydalanuvchilarga) eslatma."""
    from apps.accounts.models import User

    for recipient in User.objects.filter(role=role, is_active=True):
        Notification.objects.create(
            user=recipient,
            title=title,
            message=message,
            level=Notification.Level.WARNING,
            entity='Replenishment',
            object_id=str(replenishment.pk),
        )


# `_notify_sales_for_client_approval` olib tashlandi (10-to'plam §4):
# yangi hisob sales'ga bormaydi — sales endi faqat INFO xabar oladi
# (submit ichida). PENDING_SALES holati va approve/reject shoxi jonli
# bazadagi eski hisoblar uchun turibdi.


def _admin_threshold_skip(replenishment):
    """TOPSHIRIQ #2: chegaradan kichik UZS hisob admin tasdig'isiz o'tadimi.

    Shartnomadagi qoidalar aynan: taqqoslash QQS bilan (`total_amount` —
    logistika/boshqa xarajatlar ham ichida), faqat UZS (boshqa valyutada
    kurs yo'q — doim adminga), 0 — chegara yo'q.
    """
    from apps.core.models import CompanyProfile

    threshold = CompanyProfile.load().replenishment_approval_threshold
    return bool(
        threshold
        and replenishment.currency == 'UZS'
        and replenishment.total_amount < threshold
    )


@atomic
def approve(replenishment, user, comment=''):
    """Tasdiqlash zanjiri (TZ 9).

    Mijoz buyurtmasidan ochilgan hisobda: sales (mijoz roziligi) -> bugalter
    -> admin. Oddiy to'ldirishda: bugalter -> admin. TOPSHIRIQ #2: summa
    `replenishment_approval_threshold` dan kichik (UZS) bo'lsa admin bosqichi
    o'tkazib yuboriladi — tarixda avtomatik yozuv qoladi.
    """
    admin_skipped = False
    if replenishment.status == Replenishment.Status.PENDING_SALES:
        _require(user, sales=True)
        step = ReplenishmentApproval.Step.SALES
        replenishment.status = Replenishment.Status.PENDING_BUGALTER
    elif replenishment.status == Replenishment.Status.PENDING_BUGALTER:
        _require(user, bugalter=True)
        step = ReplenishmentApproval.Step.BUGALTER
        admin_skipped = _admin_threshold_skip(replenishment)
        replenishment.status = (
            Replenishment.Status.APPROVED if admin_skipped
            else Replenishment.Status.PENDING_ADMIN
        )
    elif replenishment.status == Replenishment.Status.PENDING_ADMIN:
        _require(user, admin=True)
        step = ReplenishmentApproval.Step.ADMIN
        replenishment.status = Replenishment.Status.APPROVED
    else:
        raise ValidationError('Hisob tasdiqlash bosqichida emas.')

    replenishment.save()
    # 4-to'plam §4: bosqich egasi qaror qildi — uning eslatmasi yopiladi
    from apps.core.services import resolve_notifications

    resolve_notifications('Replenishment', replenishment.pk, user=user)
    ReplenishmentApproval.objects.create(
        replenishment=replenishment,
        step=step,
        decision=ReplenishmentApproval.Decision.APPROVED,
        comment=comment,
        decided_by=user,
    )
    if admin_skipped:
        # Tarix jim qolmasin: nega admin ko'rmagani yozib qo'yiladi
        from apps.core.models import CompanyProfile

        threshold = CompanyProfile.load().replenishment_approval_threshold
        ReplenishmentApproval.objects.create(
            replenishment=replenishment,
            step=ReplenishmentApproval.Step.ADMIN,
            decision=ReplenishmentApproval.Decision.APPROVED,
            comment=(
                f'Summa {replenishment.total_amount} {replenishment.currency} — '
                f'chegara {threshold} dan past, admin tasdig\'i talab qilinmadi.'
            ),
            decided_by=None,
        )
    _notify_next_step(replenishment, admin_skipped=admin_skipped)
    return replenishment


def _notify_next_step(replenishment, admin_skipped=False):
    """Tasdiq zanjirida navbat kimga o'tgan bo'lsa, o'shanga xabar tushadi.

    Aks holda keyingi bosqich egasi (masalan admin) hisob unga kelganini
    bilmay qolardi — front topgan xato. `admin_skipped` — chegara tufayli
    admin chetlab o'tilgan: xabar "Admin tasdiqladi" demasin.
    """
    from apps.accounts.models import User

    if replenishment.status == Replenishment.Status.PENDING_BUGALTER:
        _notify_role(
            User.Role.BUGALTER, replenishment,
            title=f'{replenishment.number}: bugalter tekshiruvi kutilmoqda',
            message=(
                'Sales mijoz roziligini oldi — hisobni tekshirib tasdiqlang, '
                'keyin adminga o\'tadi.'
            ),
        )
    elif replenishment.status == Replenishment.Status.PENDING_ADMIN:
        _notify_role(
            User.Role.ADMIN, replenishment,
            title=f'{replenishment.number}: admin tasdig\'i kutilmoqda',
            message=(
                f'Bugalter tekshirib tasdiqladi. Summa: {replenishment.total_amount} '
                f'{replenishment.currency} — oxirgi tasdiq sizdan, keyin to\'lov bosqichi.'
            ),
        )
    elif replenishment.status == Replenishment.Status.APPROVED:
        if admin_skipped:
            pay_message = (
                f'Summa chegaradan past — admin tasdig\'i talab qilinmadi. '
                f'Summa: {replenishment.total_amount} {replenishment.currency} '
                f'— to\'lovni amalga oshiring.'
            )
            done_message = (
                'Tasdiqlandi (summa chegaradan past — admin shart emas) — '
                'to\'lov bugalterda.'
            )
        else:
            pay_message = (
                f'Admin tasdiqladi. Summa: {replenishment.total_amount} '
                f'{replenishment.currency} — to\'lovni amalga oshiring.'
            )
            done_message = 'Barcha bosqichlardan o\'tdi — to\'lov bugalterda.'
        _notify_role(
            User.Role.BUGALTER, replenishment,
            title=f'{replenishment.number}: tasdiqlandi — to\'lov bosqichi',
            message=pay_message,
        )
        if replenishment.created_by:
            Notification.objects.create(
                user=replenishment.created_by,
                title=f'{replenishment.number}: hisob to\'liq tasdiqlandi',
                message=done_message,
                level=Notification.Level.INFO,
                entity='Replenishment',
                object_id=str(replenishment.pk),
            )


@atomic
def reject(replenishment, user, comment=''):
    """Sales, bugalter yoki admin hisobni qaytaradi."""
    if replenishment.status == Replenishment.Status.PENDING_SALES:
        _require(user, sales=True)
        step = ReplenishmentApproval.Step.SALES
    elif replenishment.status == Replenishment.Status.PENDING_BUGALTER:
        _require(user, bugalter=True)
        step = ReplenishmentApproval.Step.BUGALTER
    elif replenishment.status == Replenishment.Status.PENDING_ADMIN:
        _require(user, admin=True)
        step = ReplenishmentApproval.Step.ADMIN
    else:
        raise ValidationError('Hisob tasdiqlash bosqichida emas.')

    replenishment.status = Replenishment.Status.REJECTED
    replenishment.save()
    ReplenishmentApproval.objects.create(
        replenishment=replenishment,
        step=step,
        decision=ReplenishmentApproval.Decision.REJECTED,
        comment=comment,
        decided_by=user,
    )
    if replenishment.created_by:
        Notification.objects.create(
            user=replenishment.created_by,
            title=f'{replenishment.number}: hisob qaytarildi',
            message=comment,
            level=Notification.Level.WARNING,
            entity='Replenishment',
            object_id=str(replenishment.pk),
        )
    return replenishment


@atomic
def pay(replenishment, user, *, debt_amount=None):
    """Tasdiqlangan hisobni to'lash. Pul yetmasa — farqi qarzga o'tadi (TZ 7.1).

    debt_amount berilmasa, kassadagi mavjud pulga qarab avtomatik hisoblanadi.
    """
    from apps.core.utils import parse_amount

    _require(user, bugalter=True)
    if replenishment.status != Replenishment.Status.APPROVED:
        raise ValidationError('Avval hisob admin tomonidan tasdiqlanishi kerak.')

    total = replenishment.total_amount
    available = cash_balance()
    # Front satr yoki float yuborsa ham yiqilmaydi — Decimal ga o'giriladi (400 xato bilan)
    debt_amount = parse_amount(debt_amount, 'debt_amount')
    debt_amount = replenishment.shortfall if debt_amount is None else debt_amount
    debt_amount = min(max(debt_amount, Decimal('0')), total)
    cash_part = total - debt_amount

    if cash_part > available:
        raise ValidationError({
            'detail': 'Kassada yetarli pul yo\'q.',
            'total': total,
            'cash_available': available,
            'suggested_debt': total - available,
        })

    if cash_part:
        # Yacheyka hujjat turiga qarab: chet valyuta — import, so'm — mahalliy
        # ta'minot fakturasi. (Avval supplier bo'sh-bo'shmasligiga qarab tanlanib,
        # deyarli hammasi "Boshqa xarajat"ga tushib ketardi.)
        record_transaction(
            code='contract_invoice' if replenishment.currency == 'UZS' else 'import',
            amount=cash_part,
            occurred_at=now(),
            description=f'{replenishment.number} — omborni to\'ldirish',
            currency=replenishment.currency,
            exchange_rate=replenishment.exchange_rate,
            replenishment=replenishment,
            user=user,
            approved_by=user,
        )

    if debt_amount:
        deadline = replenishment.default_debt_deadline
        loan = Loan.objects.create(
            lender_name=replenishment.supplier or 'Ta\'minotchi',
            amount=debt_amount,
            currency=replenishment.currency,
            taken_at=localdate(),
            deadline=deadline,
            source=Loan.Source.SUPPLIER,
            note=f'{replenishment.number} bo\'yicha qarz',
            created_by=user,
        )
        # TOPSHIRIQ-2 #1: ta'minotchi qarzi — MAJBURIYAT, kirim emas: hech
        # qanday pul kelmaydi, shuning uchun kassaga yozuv YO'Q. (Avval
        # 'loan' KIRIMi yozilib, kassada yo'q pul paydo bo'lar va xarajat
        # qarz summasiga kam ko'rsatilardi.) Kassa qarz bilan faqat
        # QAYTARILGANDA (loan_repay chiqimi) uchrashadi.
        replenishment.debt = loan
        # Qarz — pul ma'lumoti: faqat bugalter va adminga (hammaga emas)
        from apps.accounts.models import User

        for role in (User.Role.BUGALTER, User.Role.ADMIN):
            _notify_role(
                role, replenishment,
                title=f'{replenishment.number}: {debt_amount} qarzga o\'tqazildi',
                message=f'Muddat: {deadline}',
            )

    # To'lov paytidagi qarz muzlatiladi — keyin kassa o'zgarsa ham bu raqam turadi
    replenishment.debt_amount = debt_amount
    replenishment.paid_amount = cash_part
    replenishment.status = Replenishment.Status.ORDERED
    replenishment.save()

    # 4-to'plam §4: "to'lovni amalga oshiring" vazifasi bajarildi
    from apps.core.services import resolve_notifications

    resolve_notifications('Replenishment', replenishment.pk, user=user)

    ReplenishmentEvent.objects.create(
        replenishment=replenishment,
        stage=ReplenishmentEvent.Stage.ORDERED,
        comment='To\'lov amalga oshirildi, buyurtma berildi',
        happened_at=now(),
        created_by=user,
    )
    return replenishment


@atomic
def add_event(replenishment, user, *, stage, comment='', happened_at=None):
    """Yetkazib berish bosqichini qayd etadi (bojxona va h.k. — TZ 7.3)."""
    _require(user, supplier=True, bugalter=True)
    event = ReplenishmentEvent.objects.create(
        replenishment=replenishment,
        stage=stage,
        comment=comment,
        happened_at=happened_at or now(),
        created_by=user,
    )

    stage_to_status = {
        ReplenishmentEvent.Stage.SHIPPED: Replenishment.Status.IN_TRANSIT,
        ReplenishmentEvent.Stage.CUSTOMS: Replenishment.Status.CUSTOMS,
        ReplenishmentEvent.Stage.CLEARED: Replenishment.Status.IN_TRANSIT,
    }
    new_status = stage_to_status.get(stage)
    if new_status and replenishment.status not in {
        Replenishment.Status.DELIVERED, Replenishment.Status.CANCELLED,
    }:
        replenishment.status = new_status
        replenishment.save()
    return event


def _open_purchase_document(replenishment, user):
    """TLD receive'da KIR hujjatini avtomatik ochadi (§4.3 — TLD/KIR ulanishi).

    Hujjat tayyor `received` holatda ochiladi: ombor kirimi va kassa chiqimi
    TLD tomonida bo'lib bo'lgan, KIR faqat qog'oz izi (invoys, bojxona,
    valyuta hujjatlari) uchun. Bugalterga fayllarni biriktirish eslatmasi boradi.
    """
    from django.utils.timezone import localdate as _localdate

    from apps.accounts.models import User
    from apps.purchases.models import Purchase, PurchaseItem

    if replenishment.purchases.exists():
        return replenishment.purchases.first()

    purchase = Purchase.objects.create(
        type=Purchase.Type.LOCAL if replenishment.currency == 'UZS' else Purchase.Type.IMPORT,
        status=Purchase.Status.RECEIVED,
        supplier=replenishment.supplier or "Ta'minotchi",
        warehouse=replenishment.warehouse,
        replenishment=replenishment,
        currency=replenishment.currency,
        exchange_rate=replenishment.exchange_rate,
        received_at=_localdate(),
        note=(
            f'{replenishment.number} hisobidan avtomatik ochildi — '
            'invoys va bojxona hujjatlari shu yerga biriktiriladi. '
            "Ombor kirimi va to'lov TLD tomonida yozilgan."
        ),
        created_by=user,
    )
    for item in replenishment.items.select_related('product'):
        PurchaseItem.objects.create(
            purchase=purchase,
            product=item.product,
            quantity=item.quantity,
            unit_price=item.unit_price,
            note=f'{replenishment.number} qatoridan',
        )
    for bugalter in User.objects.filter(role=User.Role.BUGALTER, is_active=True):
        Notification.objects.create(
            user=bugalter,
            title=f'{purchase.number}: hujjatlarni biriktiring',
            message=(
                f'{replenishment.number} omborga kirim qilindi — invoys va '
                'bojxona hujjatlarini shu KIR hujjatiga yuklang.'
            ),
            level=Notification.Level.INFO,
            entity='Purchase',
            object_id=str(purchase.pk),
        )
    return purchase


@atomic
def receive(replenishment, user):
    """Mahsulot omborga kirim qilinadi; qarz muddati shu kundan hisoblanadi (TZ 7.2)."""
    _require(user, supplier=True, bugalter=True)
    if replenishment.status == Replenishment.Status.DELIVERED:
        raise ValidationError('Bu hisob allaqachon omborga kirim qilingan.')
    if replenishment.status in {Replenishment.Status.DRAFT, Replenishment.Status.PENDING_SALES,
                                Replenishment.Status.PENDING_BUGALTER,
                                Replenishment.Status.PENDING_ADMIN, Replenishment.Status.REJECTED}:
        raise ValidationError('Avval hisob tasdiqlanib, to\'lov qilinishi kerak.')

    from apps.inventory.services import update_cost_price

    for item in replenishment.items.select_related('product'):
        apply_movement(
            product=item.product,
            warehouse=replenishment.warehouse,
            type=StockMovement.Type.IN,
            quantity=item.quantity,
            reason=StockMovement.Reason.PURCHASE,
            reference=replenishment.number,
            user=user,
        )
        # Xarid narxi katalogga tushadi — aks holda mahsulot tannarxsiz
        # qolib, configurator qatori needs_price bilan qulflanardi
        update_cost_price(item.product, item.unit_price)

    # Bog'langan konfiguratsiyaning narxsiz qatorlari yangi tannarxni oladi —
    # save() ombordagi narxni o'zi to'ldiradi, sales endi yakunlay oladi
    if replenishment.configuration_id:
        for config_item in replenishment.configuration.items.filter(unit_price=0):
            config_item.save()

        # §11.4: kelgan mol egasiz qolmaydi — darhol o'sha konfiguratsiyaga
        # (chernovik bo'lsa yumshoq, shartnomasi bo'lsa qattiq) bron qilinadi
        from apps.inventory.services import (
            sync_configuration_reservations,
            sync_contract_reservations,
        )

        configuration = replenishment.configuration
        sync_configuration_reservations(configuration)
        contract = configuration.active_contract
        if contract:
            sync_contract_reservations(contract)

        # TOPSHIRIQ-2 #4C: yig'ishni bajaradigan odam (engineer) mol
        # kelganini bilsin — omborni qo'lda kuzatib o'tirmasin
        if configuration.created_by:
            Notification.objects.create(
                user=configuration.created_by,
                title=f'{configuration.number}: mol keldi — yig\'ish mumkin',
                message=(
                    f'{replenishment.number} omborga kirim qilindi. '
                    'Konfiguratsiyani yig\'ib (assemble) yakunlashingiz mumkin.'
                ),
                level=Notification.Level.INFO,
                entity='Configuration',
                object_id=str(configuration.pk),
            )

    # TOPSHIRIQ-2 #2: shartnomadan ochilgan hisob — kelgan mol darhol o'sha
    # shartnomaga band qilinadi va egasi (sales) xabar oladi
    if replenishment.contract_id:
        from apps.inventory.services import sync_contract_reservations

        contract = replenishment.contract
        sync_contract_reservations(contract)
        if contract.created_by:
            Notification.objects.create(
                user=contract.created_by,
                title=f'{contract.number}: mol keldi — yetkazish mumkin',
                message=(
                    f'{replenishment.number} omborga kirim qilindi va '
                    'shartnomaga band qilindi. Buyurtmachi yetkazishni belgilaydi.'
                ),
                level=Notification.Level.INFO,
                entity='Contract',
                object_id=str(contract.pk),
            )

    # §4.3: TLD receive o'zi KIR hujjatini ochadi — invoys/bojxona fayllari
    # shu hujjatga biriktiriladi. Ombor harakati va kassa chiqimi TLD da
    # allaqachon yozilgan, shuning uchun bu KIR hech qachon receive qilinmaydi
    # (tayyor `received` holatda ochiladi) va ikkinchi kirim/chiqim bo'lmaydi.
    _open_purchase_document(replenishment, user)

    today = localdate()
    replenishment.delivered_at = today
    replenishment.status = Replenishment.Status.DELIVERED

    # Qarz sanog'i mahsulot kelgan kundan boshlanadi
    if replenishment.debt:
        from datetime import timedelta

        replenishment.debt.taken_at = today
        replenishment.debt.deadline = today + timedelta(days=DEBT_TERM_DAYS)
        replenishment.debt.save()

    replenishment.save()
    # 4-to'plam §4: "kirim qiling" vazifasi bajarildi — qilgan odamniki yopiladi
    from apps.core.services import resolve_notifications

    resolve_notifications('Replenishment', replenishment.pk, user=user)
    ReplenishmentEvent.objects.create(
        replenishment=replenishment,
        stage=ReplenishmentEvent.Stage.ARRIVED,
        comment='Omborga kirim qilindi',
        happened_at=now(),
        created_by=user,
    )
    return replenishment
