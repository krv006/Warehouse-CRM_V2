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
    ImportCostSheet,
    PriceRequest,
    PriceRequestLine,
    Replenishment,
    ReplenishmentApproval,
    ReplenishmentEvent,
    ReplenishmentItem,
)


def _require(
    user, *, supplier=False, bugalter=False, sales=False, admin=False,
    engineer=False, logist=False, declarant=False,
):
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
    if engineer and user.is_engineer:
        return
    if logist and user.is_logist:
        return
    if declarant and user.is_declarant:
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
        # 21-§1.4: yig'ilgan variant (bir martalik, bitta buyurtma uchun)
        # yetishmayotganlar ro'yxatiga tushmasin — u qayta buyurtma
        # qilinadigan haqiqiy mahsulot emas (21-§1.0)
        Product.objects.filter(is_active=True, base_model__isnull=True)
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


# ---------------------------------------------------------------------------
# 24-to'plam: import tannarx varaqasi — tovar (buyurtmachi) → logistika
# (logist) → bojxona (deklarant), ketma-ket (§6.3: deklarant logistdan
# OLDIN yozolmaydi — bojxona qiymati ichida chegaragacha yetkazish bor).
# ---------------------------------------------------------------------------

_IMPORT_SHEET_OPEN_STATUSES = (
    ImportCostSheet.Status.DRAFT,
    ImportCostSheet.Status.WAITING_LOGISTICS,
    ImportCostSheet.Status.WAITING_CUSTOMS,
)


def _notify_import_role(role, *, title, message, entity, object_id, level=None):
    """24-to'plam: `_notify_role`dan ataylab boshqa nom — u eskidan
    (`Replenishment`ga qat'iy bog'langan, 4 pozitsion argument) shu faylda
    bor, bir xil nom bo'lsa ikkinchi ta'rif birinchisini almashtirib
    qo'yardi (butun faylda)."""
    from apps.accounts.models import User

    level = level or Notification.Level.WARNING
    for recipient in User.objects.filter(role=role, is_active=True):
        Notification.objects.create(
            user=recipient, title=title, message=message,
            level=level, entity=entity, object_id=str(object_id),
        )


@atomic
def open_import_sheet(product, user, *, quantity, configuration=None):
    """Import tannarx varaqasini ochadi (24-§6.2/§6.4).

    §7 case 15: bitta mahsulotga ikkinchi OCHIQ varaqa bo'lmaydi — ochiq
    varaqa bor bo'lsa, yangisi yaratilmay O'SHA qaytariladi (bu funksiya
    `request_prices` dan har safar qayta chaqirilishi mumkin, xuddi
    o'sha idempotent naqsh bilan — "necha marta ham chaqiriladi").
    """
    from apps.core.utils import parse_amount

    _require(user, supplier=True, engineer=True)
    existing = ImportCostSheet.objects.filter(
        product=product, status__in=_IMPORT_SHEET_OPEN_STATUSES,
    ).first()
    if existing is not None:
        return existing

    from apps.accounts.models import User
    from apps.core.models import CompanyProfile

    quantity = parse_amount(quantity, 'quantity') or Decimal('1')
    sheet = ImportCostSheet.objects.create(
        product=product, quantity=quantity, configuration=configuration,
        vat_recoverable=CompanyProfile.load().vat_recoverable,
        created_by=user,
    )
    _notify_import_role(
        User.Role.SUPPLIER,
        title=f'{sheet.number}: import tovar ma\'lumoti kerak',
        message=f'{product.name} uchun tovar narxi, valyuta va davlat kiriting.',
        entity='ImportCostSheet', object_id=sheet.pk,
    )
    return sheet


@atomic
def fill_goods_section(sheet, user, *, currency, goods_price, exchange_rate, origin_country=''):
    """A. Buyurtmachi: tovar narxi + valyuta + kurs + davlat (24-§6.2).

    §8.8: kurs qo'lda kiritiladi (bojxona deklaratsiya sanasidagi kursni
    qo'llaydi, avtomatik "bugungi kurs" hisoblarni noto'g'ri qiladi va
    buni hech kim sezmaydi) — `exchange_rate > 0` majburiy (§7 case 24).
    """
    from apps.core.utils import parse_amount

    _require(user, supplier=True)
    if sheet.status != ImportCostSheet.Status.DRAFT:
        raise ValidationError({
            'detail': "Tovar ma'lumoti faqat chernovik bosqichida kiritiladi.",
        })
    goods_price = parse_amount(goods_price, 'goods_price')
    exchange_rate = parse_amount(exchange_rate, 'exchange_rate')
    if not exchange_rate or exchange_rate <= 0:
        raise ValidationError({'exchange_rate': "Kurs 0 dan katta bo'lishi kerak."})
    if not goods_price or goods_price <= 0:
        raise ValidationError({'goods_price': "Tovar narxi 0 dan katta bo'lishi kerak."})

    sheet.currency = currency
    sheet.goods_price = goods_price
    sheet.exchange_rate = exchange_rate
    sheet.origin_country = origin_country
    sheet.goods_filled_by = user
    sheet.goods_filled_at = now()
    sheet.status = ImportCostSheet.Status.WAITING_LOGISTICS
    sheet.save()

    from apps.accounts.models import User
    from apps.core.services import resolve_notifications

    resolve_notifications('ImportCostSheet', sheet.pk, user=user)
    _notify_import_role(
        User.Role.LOGIST,
        title=f'{sheet.number}: logistika narxi kerak',
        message=f'{sheet.product.name} — {sheet.quantity} dona. Umumiy yetkazish narxini kiriting.',
        entity='ImportCostSheet', object_id=sheet.pk,
    )
    _log_import_sheet_event(sheet, 'logistics_asked', user)
    return sheet


@atomic
def fill_logistics_section(sheet, user, *, logistics_total, note=''):
    """B. Logist: bitta umumiy raqam (24-§1.3/§6.2).

    §8.2: bojxona qiymatiga qanchasi kirishini DEKLARANT belgilaydi —
    sukut qiymati shu logistika summasining O'ZI (deklarant unutsa hisob
    OSHIB chiqadi, kamaymaydi — §8.2 dagi qaror).
    """
    from apps.core.utils import parse_amount

    _require(user, logist=True)
    if sheet.status != ImportCostSheet.Status.WAITING_LOGISTICS:
        raise ValidationError({
            'detail': "Bu bosqichda logistika narxi kiritilmaydi — avval tovar ma'lumoti to'ldirilishi kerak.",
        })
    logistics_total = parse_amount(logistics_total, 'logistics_total')
    if logistics_total is None or logistics_total < 0:
        raise ValidationError({'logistics_total': "Logistika narxi manfiy bo'lmasligi kerak."})

    sheet.logistics_total = logistics_total
    sheet.logistics_note = note
    sheet.logistics_filled_by = user
    sheet.logistics_filled_at = now()
    # Deklarant ustidan yozadi; yozmasa hisob KO'PROQ chiqadi, kamroq emas (§8.2)
    sheet.freight_to_border = logistics_total
    sheet.status = ImportCostSheet.Status.WAITING_CUSTOMS
    sheet.save()

    from apps.accounts.models import User
    from apps.core.services import resolve_notifications

    resolve_notifications('ImportCostSheet', sheet.pk, user=user)
    _notify_import_role(
        User.Role.DECLARANT,
        title=f'{sheet.number}: bojxona hisobi kerak',
        message=f'{sheet.product.name} — TN VED, boj, sertifikat va boshqa xarajatlarni kiriting.',
        entity='ImportCostSheet', object_id=sheet.pk,
    )
    _log_import_sheet_event(sheet, 'logistics_given', user)
    return sheet


@atomic
def fill_customs_section(
    sheet, user, *, tnved_code, freight_to_border=None, duty_percent=0,
    duty_amount=0, excise_amount=0, vat_percent=Decimal('12'), customs_fee=None,
    certificate_cost=0, laboratory_cost=0, declarant_fee=0, note='',
):
    """C. Deklarant: TN VED, boj, sertifikat, laboratoriya, xizmat, yig'im —
    hisobni yopadi (24-§6.2/§6.3).

    §6.3: `waiting_logistics`da deklarantning maydonlari YOPIQ — bojxona
    qiymati logistika raqamiga bog'liq, deklarant uni bilmasdan hisoblasa
    natija xato bo'ladi (va bu xato hech qayerda ko'rinmaydi).
    §7 case 13: tovar narxi kiritilmagan (`goods_price=0`) bo'lsa 400 —
    nol tovar narxidan chiqadigan tannarx faqat xarajatlardan iborat bo'lardi.
    """
    from apps.core.utils import parse_amount

    _require(user, declarant=True)
    if sheet.status == ImportCostSheet.Status.WAITING_LOGISTICS:
        raise ValidationError({
            'detail': (
                "Avval logist logistika narxini yozishi kerak — "
                "bojxona qiymati unga bog'liq."
            ),
        })
    if sheet.status != ImportCostSheet.Status.WAITING_CUSTOMS:
        raise ValidationError({
            'detail': 'Bu bosqichda bojxona hisobi kiritilmaydi.',
        })
    if not sheet.goods_price:
        raise ValidationError({
            'detail': "Tovar narxi kiritilmagan — avval tovar bo'limi to'ldirilsin.",
        })

    sheet.tnved_code = tnved_code
    if freight_to_border is not None:
        sheet.freight_to_border = parse_amount(freight_to_border, 'freight_to_border')
    sheet.duty_percent = parse_amount(duty_percent, 'duty_percent') or Decimal('0')
    sheet.duty_amount = parse_amount(duty_amount, 'duty_amount') or Decimal('0')
    sheet.excise_amount = parse_amount(excise_amount, 'excise_amount') or Decimal('0')
    sheet.vat_percent = parse_amount(vat_percent, 'vat_percent') or Decimal('0')
    parsed_customs_fee = parse_amount(customs_fee, 'customs_fee')
    if parsed_customs_fee is None:
        from apps.core.models import CompanyProfile

        parsed_customs_fee = CompanyProfile.load().default_customs_fee
    sheet.customs_fee = parsed_customs_fee or Decimal('0')
    sheet.certificate_cost = parse_amount(certificate_cost, 'certificate_cost') or Decimal('0')
    sheet.laboratory_cost = parse_amount(laboratory_cost, 'laboratory_cost') or Decimal('0')
    sheet.declarant_fee = parse_amount(declarant_fee, 'declarant_fee') or Decimal('0')
    sheet.customs_note = note
    sheet.customs_filled_by = user
    sheet.customs_filled_at = now()
    sheet.status = ImportCostSheet.Status.DONE
    sheet.save()

    product = sheet.product
    # §7 case 9: kod o'zgargani ActivityLog'da ko'rinsin
    if product.tnved_code != tnved_code:
        from apps.core.models import ActivityLog

        ActivityLog.objects.create(
            user=user, action=ActivityLog.Action.UPDATE, entity='Product',
            object_id=str(product.pk),
            description=f'TN VED kodi: "{product.tnved_code}" → "{tnved_code}" ({sheet.number})',
        )
    product.tnved_code = tnved_code
    product.cost_price = sheet.unit_cost
    product.save(update_fields=['tnved_code', 'cost_price'])

    from apps.configurator.services import price_arrived
    from apps.core.services import resolve_notifications

    resolve_notifications('ImportCostSheet', sheet.pk, user=user)
    price_arrived(product, user)
    _log_import_sheet_event(sheet, 'customs_given', user)
    return sheet


def _log_import_sheet_event(sheet, stage, user):
    """24-§6.7: varaqa bosqichi zayavka tarixiga ham tushadi — sheet ochilgan
    zanjir (`configuration`) bo'lsa. Mustaqil (ombordan to'g'ridan) ochilgan
    varaqada zanjir yo'q — jim o'tkaziladi (`log_request_event` `None`ni bilardi)."""
    if not sheet.configuration_id:
        return
    from apps.configurator.models import ConfigurationRequestEvent
    from apps.configurator.services import _owning_request, log_request_event

    request_obj = _owning_request(sheet.configuration)
    log_request_event(
        request_obj, getattr(ConfigurationRequestEvent.Stage, stage.upper()),
        user, sheet.product.name,
    )


@atomic
def return_import_sheet(sheet, user, comment):
    """Logist/deklarant — ma'lumot yetmasa orqaga (24-§7 case 10)."""
    _require(user, logist=True, declarant=True)
    if not comment:
        raise ValidationError({'comment': 'Izoh majburiy.'})
    if sheet.status not in (
        ImportCostSheet.Status.WAITING_LOGISTICS, ImportCostSheet.Status.WAITING_CUSTOMS,
    ):
        raise ValidationError({'detail': 'Bu varaqa hozir qaytarib bo\'lmaydigan bosqichda.'})

    sheet.status = ImportCostSheet.Status.DRAFT
    sheet.save()

    from apps.accounts.models import User
    from apps.core.services import resolve_notifications

    resolve_notifications('ImportCostSheet', sheet.pk, user=user)
    if sheet.created_by_id:
        Notification.objects.create(
            user=sheet.created_by,
            title=f'{sheet.number}: qaytarildi',
            message=comment,
            level=Notification.Level.WARNING,
            entity='ImportCostSheet', object_id=str(sheet.pk),
        )
    _notify_import_role(
        User.Role.SUPPLIER,
        title=f'{sheet.number}: qaytarildi — tuzatish kerak',
        message=comment,
        entity='ImportCostSheet', object_id=sheet.pk,
    )
    return sheet


@atomic
def cancel_import_sheet(sheet, user, reason=''):
    """Admin yoki ochgan odam — ochiq varaqani bekor qiladi (24-§7 case 16)."""
    if not (user.is_admin or user.id == sheet.created_by_id):
        raise PermissionDenied("Bu varaqani faqat admin yoki ochgan odam bekor qiladi.")
    if sheet.status == ImportCostSheet.Status.CANCELLED:
        raise ValidationError({'detail': 'Bu varaqa allaqachon bekor qilingan.'})

    sheet.status = ImportCostSheet.Status.CANCELLED
    sheet.save()

    from apps.core.models import ActivityLog
    from apps.core.services import resolve_notifications

    ActivityLog.objects.create(
        user=user, action=ActivityLog.Action.UPDATE, entity='ImportCostSheet',
        object_id=str(sheet.pk), description=reason or f'{sheet.number} bekor qilindi',
    )
    resolve_notifications('ImportCostSheet', sheet.pk)
    return sheet


@atomic
def change_import_sheet_quantity(sheet, user, quantity):
    """Miqdor o'zgardi — dona tannarx qayta hisoblanadi, lekin LOGISTIKA
    raqami eskiradi (24-§7 case 6): varaqa `waiting_logistics`ga qaytadi,
    logistga eslatma. Yopilgan (`done`)/bekor qilingan varaqa tahrirlanmaydi
    (§7 case 11 — yangi import uchun yangi varaqa ochiladi)."""
    from apps.core.utils import parse_amount

    _require(user, supplier=True, engineer=True)
    if sheet.status in (ImportCostSheet.Status.DONE, ImportCostSheet.Status.CANCELLED):
        raise ValidationError({
            'detail': 'Yopilgan yoki bekor qilingan varaqa tahrirlanmaydi — yangisini oching.',
        })
    quantity = parse_amount(quantity, 'quantity')
    if not quantity or quantity <= 0:
        raise ValidationError({'quantity': "Miqdor 0 dan katta bo'lishi kerak."})

    sheet.quantity = quantity
    needs_relogistics = sheet.status == ImportCostSheet.Status.WAITING_CUSTOMS
    if needs_relogistics:
        sheet.status = ImportCostSheet.Status.WAITING_LOGISTICS
    sheet.save()

    if needs_relogistics:
        from apps.accounts.models import User

        _notify_import_role(
            User.Role.LOGIST,
            title=f'{sheet.number}: miqdor o\'zgardi — logistika narxi qayta kerak',
            message=f'{sheet.product.name}: yangi miqdor {quantity}. Yetkazish narxini qayta tasdiqlang.',
            entity='ImportCostSheet', object_id=sheet.pk,
        )
    return sheet


# ---------------------------------------------------------------------------
# 28-to'plam: narx so'rovi — BITTA hujjat, uch rol, bir-birini ko'rmaydi.
#
# `ImportCostSheet` (24-to'plam, yuqorida) TEGILMAYDI — model, arifmetika va
# uning 38 testi saqlanadi, lekin endi `configurator.request_prices` uni
# ochmaydi (28-§4). Yangi oqim mustaqil: bitta `PriceRequest` konfiguratsiya
# uchun narxsiz NARSALARNI (butlovchi YOKI `order` rejimidagi bazaviy model,
# 26-§1(c)) bitta hujjatga yig'adi, import bo'lsa qatorning ICHIDA logist va
# deklarant bosqichlaridan o'tadi.
# ---------------------------------------------------------------------------

_PRICE_REQUEST_STATUS_SEVERITY = {
    PriceRequest.Status.WAITING_LOGISTICS: 0,
    PriceRequest.Status.WAITING_CUSTOMS: 1,
    PriceRequest.Status.WAITING_SUPPLIER: 2,
    PriceRequest.Status.ANSWERED: 3,
}

_PRICE_REQUEST_OPEN_STATUSES = (
    PriceRequest.Status.WAITING_LOGISTICS,
    PriceRequest.Status.WAITING_CUSTOMS,
    PriceRequest.Status.WAITING_SUPPLIER,
)


def _sync_price_request_notifications(price_request):
    """28-§2/§5(c): har rol FAQAT o'zining navbati kelganda xabar oladi —
    bitta so'rovda mahalliy va import qatorlar aralash bo'lsa (case 5),
    ikkala rol bir vaqtda ham band bo'lishi mumkin."""
    from apps.accounts.models import User
    from apps.core.services import resolve_notifications

    lines = list(price_request.lines.all())
    stage_info = {
        User.Role.LOGIST: (
            any(line.status == PriceRequest.Status.WAITING_LOGISTICS for line in lines),
            'Logistika narxi kerak', "yetkazish narxini kiriting.",
        ),
        User.Role.DECLARANT: (
            any(line.status == PriceRequest.Status.WAITING_CUSTOMS for line in lines),
            'Bojxona hisobi kerak', "TN VED, boj stavkasi va xarajatlarni kiriting.",
        ),
        User.Role.SUPPLIER: (
            any(line.status == PriceRequest.Status.WAITING_SUPPLIER for line in lines),
            'Tannarx kerak', "tovar narxi va yakuniy tannarxni kiriting.",
        ),
    }
    for role, (is_pending, title_suffix, message) in stage_info.items():
        if is_pending:
            for recipient in User.objects.filter(role=role, is_active=True):
                Notification.objects.update_or_create(
                    user=recipient, entity='PriceRequest',
                    object_id=str(price_request.pk), is_read=False,
                    defaults={
                        'title': f'{price_request.number}: {title_suffix}',
                        'message': f'{price_request.configuration.number} — {message}',
                        'level': Notification.Level.WARNING,
                    },
                )
        else:
            for recipient in User.objects.filter(role=role, is_active=True):
                resolve_notifications('PriceRequest', price_request.pk, user=recipient)


def _sync_price_request_status(price_request):
    """28-§1: `status` QATORLARDAN hisoblanadi — ENG ORQADAGI (eng kam
    bajarilgan) qator bosqichi. `cancelled` bu yerda hech qachon qo'yilmaydi."""
    if price_request.status == PriceRequest.Status.CANCELLED:
        return
    lines = list(price_request.lines.all())
    if lines:
        new_status = min(
            lines, key=lambda line: _PRICE_REQUEST_STATUS_SEVERITY[line.status],
        ).status
        if price_request.status != new_status:
            price_request.status = new_status
            price_request.save()
    _sync_price_request_notifications(price_request)


def sync_price_request_line_quantities(configuration, new_quantity):
    """29-§4(b): partiya o'zgarganda ochiq so'rov qatorlari ham ergashadi.

    24-§7 case 6 dagi qoida bilan bir xil: miqdor o'zgarsa import
    qatorning LOGISTIKA raqami eskiradi (`waiting_logistics`ga qaytadi) —
    boj STAVKASI (bojxona qismi) esa miqdorga bog'liq emas, saqlanadi.
    Javob allaqachon berilgan qatorlarga tegilmaydi.
    """
    open_requests = list(
        PriceRequest.objects.filter(
            configuration=configuration,
        ).exclude(status__in=(PriceRequest.Status.ANSWERED, PriceRequest.Status.CANCELLED))
    )
    if not open_requests:
        return

    item_quantities = {
        item.component_id: item.quantity for item in configuration.items.all()
    }
    is_order_mode = configuration.mode == configuration.Mode.ORDER

    for price_request in open_requests:
        logistics_reset = False
        for line in price_request.lines.filter(answered_at__isnull=True):
            if is_order_mode and line.product_id == configuration.base_product_id:
                new_line_quantity = Decimal(new_quantity)
            elif line.product_id in item_quantities:
                new_line_quantity = item_quantities[line.product_id] * new_quantity
            else:
                continue
            if line.quantity == new_line_quantity:
                continue
            line.quantity = new_line_quantity
            if line.is_imported and line.logistics_filled_at:
                line.logistics_filled_at = None
                logistics_reset = True
            line.save()
        _sync_price_request_status(price_request)
        if logistics_reset:
            from apps.accounts.models import User

            for logist in User.objects.filter(role=User.Role.LOGIST, is_active=True):
                Notification.objects.create(
                    user=logist,
                    title=f'{price_request.number}: miqdor o\'zgardi — logistika narxi qayta kerak',
                    message=(
                        f'{configuration.number}: yangi partiya {new_quantity}. '
                        'Yetkazish narxini qayta tasdiqlang.'
                    ),
                    level=Notification.Level.WARNING,
                    entity='PriceRequest', object_id=str(price_request.pk),
                )


def open_price_request(configuration, user, *, lines, imported_products=None):
    """28-§1: engineer so'ragan narxlarni BITTA hujjatga yig'adi.

    `lines` — [(product, quantity), ...]: chaqiruvchi (`configurator.
    services.request_prices`) build/modify uchun narxsiz butlovchilarni,
    `order` uchun bazaviy modelning o'zini (26-§1(c)) tayyorlaydi.

    Necha marta ham chaqirilishi mumkin (eski `request_prices` xulqi) —
    ochiq hujjat bo'lsa, unda yo'q mahsulotlar UNGA qo'shiladi, ikkinchi
    hujjat ochilmaydi.
    """
    _require(user, engineer=True)

    price_request = PriceRequest.objects.filter(
        configuration=configuration, status__in=_PRICE_REQUEST_OPEN_STATUSES,
    ).first()
    if price_request is None:
        price_request = PriceRequest.objects.create(configuration=configuration, created_by=user)

    from apps.core.models import CompanyProfile

    existing_product_ids = set(price_request.lines.values_list('product_id', flat=True))
    vat_recoverable = CompanyProfile.load().vat_recoverable
    for product, quantity in lines:
        if product.id in existing_product_ids:
            continue
        is_imported = product.is_imported or bool(
            imported_products and product.id in imported_products
        )
        line = PriceRequestLine(
            request=price_request, product=product, quantity=quantity,
            is_imported=is_imported, vat_recoverable=vat_recoverable,
        )
        if is_imported and not product.is_imported:
            Product.objects.filter(pk=product.id).update(is_imported=True)
        if is_imported and product.tnved_code:
            # 28-§3: kod va stavka oxirgi importdan eslab qolingan —
            # deklarant bosqichi o'tkazib yuboriladi
            line.tnved_code = product.tnved_code
            line.duty_percent = product.duty_percent
            line.certificate_cost = product.certificate_cost
            line.laboratory_cost = product.laboratory_cost
            line.customs_filled_at = now()
            line.customs_auto_filled = True
        line.save()

    _sync_price_request_status(price_request)
    return price_request


@atomic
def close_local_price_request_lines_for_product(product, user):
    """28-§1 case 1: mahalliy qator narxi `PriceRequestLine.answer` orqali
    emas, to'g'ridan `PATCH /products/{id}/` orqali ham kelishi mumkin
    (buyurtmachi mahsulot kartasida tannarx kiritishi — bugungi B2 yo'li).
    Bunday holda tegishli ochiq qatorlar/hujjatlar o'zi yopilsin — aks
    holda eslatma abadiy ochiq qolib, `answered_at`/`cost_price` hech
    qachon to'lmas edi. Import qatorga tegilmaydi — u logist/deklarant
    bosqichlaridan o'tishi shart, mahsulot narxi ular hali ishlamasdan
    o'zi yopilib ketmasin."""
    lines = PriceRequestLine.objects.filter(
        product=product, is_imported=False, answered_at__isnull=True,
    ).exclude(request__status=PriceRequest.Status.CANCELLED).select_related('request')
    for line in lines:
        line.cost_price = product.cost_price
        line.answered_at = now()
        line.save()
        _sync_price_request_status(line.request)


@atomic
def fill_price_request_logistics(line, user, *, logistics_total, freight_to_border=None, note=''):
    """28-§2: Logist — jami yetkazish narxi + shundan CHEGARAGACHA qismi.

    §5 case 9: chegaragacha yozilmasa sukut — JAMI summaning o'zi (24-§8.2
    dagi qaror bilan bir xil: hisob oshib chiqadi, kamaymaydi)."""
    from apps.core.utils import parse_amount

    _require(user, logist=True)
    if not line.is_imported:
        raise ValidationError({'detail': "Bu qator import emas — logistika kerak emas."})
    if line.answered_at:
        raise ValidationError({'detail': "Bu qator allaqachon javob olgan."})

    logistics_total = parse_amount(logistics_total, 'logistics_total') or Decimal('0')
    if logistics_total < 0:
        raise ValidationError({'logistics_total': "Logistika narxi manfiy bo'lmasligi kerak."})
    parsed_border = parse_amount(freight_to_border, 'freight_to_border')

    line.logistics_total = logistics_total
    line.freight_to_border = parsed_border if parsed_border is not None else logistics_total
    line.logistics_note = note
    line.logistics_filled_at = now()
    line.logistics_filled_by = user
    line.save()
    _sync_price_request_status(line.request)
    return line


@atomic
def fill_price_request_customs(
    line, user, *, tnved_code, duty_percent=0, duty_amount=0, excise_amount=0,
    customs_fee=None, certificate_cost=0, laboratory_cost=0, declarant_fee=0, note='',
):
    """28-§2(b): Deklarant — summa emas, STAVKA (`duty_percent`) yozadi;
    tovar narxi va logistika unga ko'rinmaydi (izolyatsiya — serializerda)."""
    from apps.core.utils import parse_amount

    _require(user, declarant=True)
    if not line.is_imported:
        raise ValidationError({'detail': 'Bu qator import emas.'})
    if line.answered_at:
        raise ValidationError({'detail': "Bu qator allaqachon javob olgan."})
    if not line.logistics_filled_at:
        raise ValidationError({
            'detail': "Avval logist logistika narxini yozishi kerak — bojxona qiymati unga bog'liq.",
        })

    line.tnved_code = tnved_code
    line.duty_percent = parse_amount(duty_percent, 'duty_percent') or Decimal('0')
    line.duty_amount = parse_amount(duty_amount, 'duty_amount') or Decimal('0')
    line.excise_amount = parse_amount(excise_amount, 'excise_amount') or Decimal('0')
    parsed_fee = parse_amount(customs_fee, 'customs_fee')
    if parsed_fee is None:
        from apps.core.models import CompanyProfile

        parsed_fee = CompanyProfile.load().default_customs_fee
    line.customs_fee = parsed_fee or Decimal('0')
    line.certificate_cost = parse_amount(certificate_cost, 'certificate_cost') or Decimal('0')
    line.laboratory_cost = parse_amount(laboratory_cost, 'laboratory_cost') or Decimal('0')
    line.declarant_fee = parse_amount(declarant_fee, 'declarant_fee') or Decimal('0')
    line.customs_note = note
    line.customs_filled_at = now()
    line.customs_auto_filled = False
    line.customs_filled_by = user
    line.save()

    # 28-§3: keyingi importda eslab qolinsin — deklarant o'tkazib yuboriladi
    product = line.product
    product.tnved_code = tnved_code
    product.duty_percent = line.duty_percent
    product.certificate_cost = line.certificate_cost
    product.laboratory_cost = line.laboratory_cost
    product.save(update_fields=['tnved_code', 'duty_percent', 'certificate_cost', 'laboratory_cost'])

    _sync_price_request_status(line.request)
    return line


@atomic
def send_price_request_line_to_customs(line, user):
    """28-§3 case 4: "Deklarantga yuborish" — avtomatik o'tkazilgan qatorga
    buyurtmachi shubhalanadi, qator qayta deklarant navbatiga qaytadi."""
    _require(user, supplier=True)
    if not line.is_imported:
        raise ValidationError({'detail': 'Bu qator import emas.'})
    if line.answered_at:
        raise ValidationError({'detail': "Bu qator allaqachon javob olgan."})
    if not line.customs_filled_at:
        raise ValidationError({'detail': "Bu qator hali deklarant navbatida."})

    line.customs_filled_at = None
    line.customs_auto_filled = False
    line.customs_filled_by = None
    line.save()
    _sync_price_request_status(line.request)
    return line


@atomic
def mark_price_request_line_imported(line, user):
    """28-§1: qatorni import deb FAQAT buyurtmachi belgilaydi — mol qayerdan
    kelishini bilgan yagona odam u. Bayroq Product'ga ham yoziladi (natija,
    shart emas) — keyingi safar qator o'zi import bo'lib ochiladi."""
    _require(user, supplier=True)
    if line.answered_at:
        raise ValidationError({'detail': "Bu qator allaqachon javob olgan."})
    if line.is_imported:
        return line

    line.is_imported = True
    product = line.product
    if not product.is_imported:
        product.is_imported = True
        product.save(update_fields=['is_imported'])
    if product.tnved_code:
        line.tnved_code = product.tnved_code
        line.duty_percent = product.duty_percent
        line.certificate_cost = product.certificate_cost
        line.laboratory_cost = product.laboratory_cost
        line.customs_filled_at = now()
        line.customs_auto_filled = True
    line.save()
    _sync_price_request_status(line.request)
    return line


@atomic
def return_price_request_line(line, user, comment):
    """29-§4(a): logist yuk tashiy olmasa yoki deklarant ma'lumot yetmasa —
    izoh bilan buyurtmachiga qaytaradi (24-to'plamdagi `return_import_sheet`
    bilan bir xil naqsh: orqaga yo'l bo'lmasa hujjat abadiy osilib qolardi).

    Import deb belgilash ham bekor qilinadi — bu urinish muvaffaqiyatsiz
    tugadi, buyurtmachi qaytadan hal qiladi (boshqa yo'l bilan import
    qiladimi, mahalliy qoladimi)."""
    _require(user, logist=True, declarant=True)
    if not (comment or '').strip():
        raise ValidationError({'comment': 'Izoh majburiy.'})
    if line.answered_at:
        raise ValidationError({'detail': "Bu qator allaqachon javob olgan."})
    if line.status not in (PriceRequest.Status.WAITING_LOGISTICS, PriceRequest.Status.WAITING_CUSTOMS):
        raise ValidationError({'detail': "Bu qator hozir qaytarib bo'lmaydigan bosqichda."})

    line.is_imported = False
    line.logistics_filled_at = None
    line.logistics_filled_by = None
    line.customs_filled_at = None
    line.customs_auto_filled = False
    line.customs_filled_by = None
    line.save()
    _sync_price_request_status(line.request)

    from apps.accounts.models import User

    role_label = 'Logist' if user.is_logist else ('Deklarant' if user.is_declarant else 'Admin')
    for supplier in User.objects.filter(role=User.Role.SUPPLIER, is_active=True):
        Notification.objects.update_or_create(
            user=supplier, entity='PriceRequest',
            object_id=str(line.request_id), is_read=False,
            defaults={
                'title': f'{line.request.number}: qaytarildi — {line.product.name}',
                'message': f'{role_label}: {comment}',
                'level': Notification.Level.WARNING,
            },
        )
    return line


@atomic
def fill_price_request_goods(
    line, user, *, currency, goods_price, exchange_rate=None, extra_costs=0,
):
    """30-§2: Buyurtmachi — tovar narxi (BITTA DONAGA, 30-§3) + qo'shimcha
    xarajatlar; qatorni YOPMAYDI. Logist/deklarant naqshi bilan bir xil:
    ikki bosqichli — avval ma'lumot, keyin alohida `answer` bilan yakun.
    Shu tufayli buyurtmachi `suggested_cost`ni KO'RIB, keyin tasdiqlaydi
    yoki ustidan yozadi — avval bu qadam yo'q edi, ko'r-ko'rona imzolanardi.

    Necha marta ham chaqirilishi mumkin (case 2: kurs xato terilgan
    bo'lishi mumkin) — `answer` esa bir marta."""
    from apps.core.utils import parse_amount

    _require(user, supplier=True)
    if line.answered_at:
        raise ValidationError({'detail': "Bu qator allaqachon javob olgan."})

    currency = currency or line.currency or 'USD'
    parsed_goods = parse_amount(goods_price, 'goods_price')
    parsed_rate = parse_amount(exchange_rate, 'exchange_rate')
    if currency == 'UZS':
        parsed_rate = Decimal('1')  # §7 case 16
    if not parsed_goods or parsed_goods <= 0:
        raise ValidationError({'goods_price': "Tovar narxi 0 dan katta bo'lishi kerak."})
    if not parsed_rate or parsed_rate <= 0:
        raise ValidationError({'exchange_rate': "Kurs 0 dan katta bo'lishi kerak."})

    line.currency = currency
    line.goods_price = parsed_goods
    line.exchange_rate = parsed_rate
    line.extra_costs = parse_amount(extra_costs, 'extra_costs') or Decimal('0')
    line.save()
    return line


@atomic
def answer_price_request_line(line, user, *, cost_price=None):
    """28-§1/§2/30-§2: Buyurtmachi yakunlaydi.

    Mahalliy qator (case 1): faqat `cost_price` katakka yoziladi. Import
    qator: tovar narxi `fill_price_request_goods` orqali OLDINDAN
    kiritilgan bo'lishi shart (30-§2 case 5) — tizim `suggested_cost`ni
    hisoblab beradi, buyurtmachi bo'sh `cost_price` bilan tasdiqlaydi
    yoki o'z raqamini yozadi (case 11)."""
    from apps.core.utils import parse_amount

    _require(user, supplier=True)
    if line.answered_at:
        raise ValidationError({'detail': "Bu qator allaqachon javob olgan."})
    if line.is_imported and not line.logistics_filled_at:
        raise ValidationError({'detail': "Logistika narxi hali kiritilmagan."})
    if line.is_imported and not line.customs_filled_at:
        raise ValidationError({'detail': "Bojxona hisobi hali kiritilmagan."})

    if line.is_imported:
        if not line.goods_price:
            raise ValidationError({
                'detail': "Tovar narxi hali kiritilmagan — avval fill-goods chaqiring.",
            })
        final_cost = parse_amount(cost_price, 'cost_price')
        if final_cost is None:
            final_cost = line.suggested_cost
    else:
        final_cost = parse_amount(cost_price, 'cost_price')
        if not final_cost or final_cost <= 0:
            raise ValidationError({'cost_price': "Tannarx 0 dan katta bo'lishi kerak."})

    line.cost_price = final_cost
    line.answered_at = now()
    line.save()

    product = line.product
    product.cost_price = final_cost
    product.save(update_fields=['cost_price'])

    _sync_price_request_status(line.request)

    from apps.configurator.services import price_arrived

    price_arrived(product, user)
    return line


@atomic
def _cancel_price_request(price_request, user, reason=''):
    """Ruxsatni tekshirmaydigan yadro — `cancel_price_request` (odam
    chaqiradi) va `configurator.cancel_chain` (butun zanjirni bekor
    qilish — 29-§4(c), ruxsat allaqachon tashqi funksiyada tekshirilgan)
    ikkalasi ham shu yerdan o'tadi."""
    if price_request.status in (PriceRequest.Status.ANSWERED, PriceRequest.Status.CANCELLED):
        return price_request

    price_request.status = PriceRequest.Status.CANCELLED
    price_request.save()

    from apps.accounts.models import User
    from apps.core.services import resolve_notifications

    for role in (User.Role.LOGIST, User.Role.DECLARANT, User.Role.SUPPLIER):
        for recipient in User.objects.filter(role=role, is_active=True):
            resolve_notifications('PriceRequest', price_request.pk, user=recipient)

    from apps.core.models import ActivityLog

    ActivityLog.objects.create(
        user=user, action=ActivityLog.Action.UPDATE, entity='PriceRequest',
        object_id=str(price_request.pk), description=reason or f'{price_request.number} bekor qilindi',
    )
    return price_request


def cancel_price_request(price_request, user, reason=''):
    """Admin yoki ochgan odam — ochiq so'rovni bekor qiladi (§6 case 12)."""
    if not (user.is_admin or user.id == price_request.created_by_id):
        raise PermissionDenied("Bu so'rovni faqat admin yoki ochgan odam bekor qiladi.")
    if price_request.status in (PriceRequest.Status.ANSWERED, PriceRequest.Status.CANCELLED):
        raise ValidationError({'detail': "Bu so'rov allaqachon yakunlangan yoki bekor qilingan."})
    return _cancel_price_request(price_request, user, reason)
