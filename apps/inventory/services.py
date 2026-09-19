from django.db.models import Sum
from django.db.transaction import atomic

from apps.inventory.models import Stock, StockMovement


def main_warehouse():
    """Tizimdagi yagona ombor — biznesda bitta ombor bor (filial yo'q).

    Ombor hali ochilmagan bo'lsa "Asosiy ombor" yaratib qaytaradi, shuning
    uchun jarayonlar hech qachon "ombor tanlanmagan" deb to'xtab qolmaydi.
    """
    from apps.inventory.models import Warehouse

    warehouse = Warehouse.objects.filter(is_active=True).order_by('id').first()
    if warehouse is None:
        warehouse = Warehouse.objects.first()
    if warehouse is None:
        warehouse = Warehouse.objects.create(name='Asosiy ombor')
    return warehouse


def available_quantity(product, warehouse=None):
    """Mahsulotning ombordagi (yoki barcha omborlardagi) qoldigi."""
    stocks = Stock.objects.filter(product=product)
    if warehouse is not None:
        stocks = stocks.filter(warehouse=warehouse)
    return stocks.aggregate(t=Sum('quantity'))['t'] or 0


@atomic
def apply_movement(*, product, warehouse, type, quantity,
                   reason=StockMovement.Reason.MANUAL, reference='', note='', user=None):
    """Harakatni yozib, ombor qoldigini yangilaydi."""
    movement = StockMovement.objects.create(
        product=product,
        warehouse=warehouse,
        type=type,
        reason=reason,
        quantity=quantity,
        reference=reference,
        note=note,
        created_by=user,
    )
    sync_stock(movement)
    return movement


@atomic
def sync_stock(movement):
    """StockMovement bo'yicha Stock qoldigini hisoblaydi."""
    stock, _ = Stock.objects.select_for_update().get_or_create(
        product=movement.product,
        warehouse=movement.warehouse,
    )
    if movement.type == StockMovement.Type.IN:
        stock.quantity += movement.quantity
    elif movement.type == StockMovement.Type.OUT:
        stock.quantity -= movement.quantity
    else:  # ADJUST — quantity yakuniy qoldiqni bildiradi
        stock.quantity = movement.quantity
    stock.save()
    return stock


# ---------------------------------------------------------------- Bron (§11.4)

def reserved_quantity(product, warehouse=None, *, kind=None,
                      exclude_contract=None, exclude_configuration=None):
    """Faol bron yig'indisi — turlari va istisnolari bilan."""
    from apps.inventory.models import StockReservation

    qs = StockReservation.objects.filter(
        product=product, status=StockReservation.Status.ACTIVE,
    )
    if warehouse is not None:
        qs = qs.filter(warehouse=warehouse)
    if kind is not None:
        qs = qs.filter(kind=kind)
    if exclude_contract is not None:
        qs = qs.exclude(contract=exclude_contract)
    if exclude_configuration is not None:
        qs = qs.exclude(configuration=exclude_configuration)
    return qs.aggregate(t=Sum('quantity'))['t'] or 0


def sellable_quantity(product, warehouse=None, *, for_contract=None,
                      for_configuration=None):
    """Erkin qoldiq = Jami − qattiq bron. Sotish uchun ochiq raqam.

    Umumiy qoida (§11.4): har qanday amal O'ZINING bronini o'ziga ochiq deb
    hisoblaydi — `for_contract`/`for_configuration` bering, aks holda hujjat
    o'z broni bilan o'zini bloklab qo'yadi. YANGI-OQIM B5 da to'langan
    konfiguratsiyaning broni ham QATTIQ — yig'ishda o'ziga ochiq bo'lsin.
    """
    from apps.inventory.models import StockReservation

    return available_quantity(product, warehouse) - reserved_quantity(
        product, warehouse,
        kind=StockReservation.Kind.HARD,
        exclude_contract=for_contract,
        exclude_configuration=for_configuration,
    )


def plannable_quantity(product, warehouse=None, *, for_configuration=None):
    """Rejadan keyin = Jami − Band − Rejada. Rejalash uchun xavfsiz raqam.

    Engineer konfiguratsiyada shu raqamni ko'radi — boshqa hujjatlarga va'da
    qilingan mol "bor" bo'lib ko'rinmaydi (o'z rejasi hisobga olinmaydi).
    YANGI-OQIM B5: o'z broni QATTIQ bo'lib qolgan (to'lov kelgan) bo'lsa ham
    o'ziga ochiq — aks holda konfiguratsiya o'z moliga o'zi yetisholmay qolardi.
    """
    from apps.inventory.models import StockReservation

    return (
        available_quantity(product, warehouse)
        - reserved_quantity(
            product, warehouse,
            kind=StockReservation.Kind.HARD,
            exclude_configuration=for_configuration,
        )
        - reserved_quantity(
            product, warehouse,
            kind=StockReservation.Kind.SOFT,
            exclude_configuration=for_configuration,
        )
    )


def _reservation_expiry(kind):
    """Bron muddati — admin CompanyProfile'da belgilaydi (0 — muddat yo'q)."""
    from datetime import timedelta

    from django.utils.timezone import localdate

    from apps.core.models import CompanyProfile
    from apps.inventory.models import StockReservation

    profile = CompanyProfile.load()
    days = (
        profile.contract_reservation_days
        if kind == StockReservation.Kind.HARD
        else profile.configuration_reservation_days
    )
    return localdate() + timedelta(days=days) if days else None


def release_reservations(*, contract=None, configuration=None,
                         status=None, user=None, note=''):
    """Hujjatning faol bronlarini bo'shatadi (released/shipped/expired)."""
    from apps.inventory.models import StockReservation

    status = status or StockReservation.Status.RELEASED
    qs = StockReservation.objects.filter(status=StockReservation.Status.ACTIVE)
    if contract is not None:
        qs = qs.filter(contract=contract)
    if configuration is not None:
        qs = qs.filter(configuration=configuration)
    return qs.update(status=status, released_by=user, release_note=note)


def _contract_needs(contract, warehouse):
    """Shartnoma nimani band qilishi kerak: {product: miqdor}.

    Yig'ilmagan variant (build rejimi, §10.1) omborda yo'q — unga bron qo'yib
    bo'lmaydi, shuning uchun bron uning BUTLOVCHILARIGA tushadi; to'lov paytida
    butlovchilar chiqib, yig'ilgan variant chiqim bo'ladi.
    """
    needs = {}
    configuration = contract.configuration
    for item in contract.items.select_related('product'):
        product = item.product
        if (
            configuration is not None
            and configuration.variant_id == product.pk
            and available_quantity(product, warehouse) < item.quantity
        ):
            for config_item in configuration.items.select_related('component'):
                component = config_item.component
                needs[component] = (
                    needs.get(component, 0) + config_item.quantity * item.quantity
                )
        else:
            needs[product] = needs.get(product, 0) + item.quantity
    return needs


def sync_contract_reservations(contract):
    """Shartnomaning qattiq bronini qatorlariga moslab qayta quradi (§11.4).

    Bor qismi band qilinadi, yetmagani "kutilmoqda" — shartnoma tuzish
    to'silmaydi (yumshoq yo'l), lekin yetishmovchilik darhol ko'rinadi.
    """
    from apps.sales.models import Contract
    from apps.inventory.models import StockReservation

    closed = {
        Contract.Status.REJECTED, Contract.Status.CANCELLED,
        Contract.Status.COMPLETED,
    }
    if contract.status in closed:
        release_reservations(contract=contract)
        return
    # YANGI OQIM: `active` = pul keldi, hali YETKAZILMAGAN (chiqim `ship`da).
    # Yetkazilganidan keyingina bron "shipped" bo'lib turadi; ungacha to'langan
    # mol albatta band bo'lishi kerak — §3.2 dagi teshik shu yerda yopiladi
    if contract.status == Contract.Status.ACTIVE and contract.delivered_at:
        return  # chiqim bo'lib bo'lgan — bron shipped holatda turadi

    # YANGI-OQIM B5.1: konfiguratsiyaga bog'langan shartnoma, konfiguratsiya
    # tayyor bo'lmaguncha (`ready`/`sold`), O'Z bronini qo'ymaydi — molni
    # ushlab turish CFG ning ishi. Aks holda bitta zanjir uchun ombordan
    # ikki marta mol band bo'lardi (§3.2): butlovchilar ham, model ham.
    configuration = contract.configuration
    if configuration is not None and configuration.status not in {
        configuration.Status.READY, configuration.Status.SOLD,
    }:
        return

    warehouse = main_warehouse()
    StockReservation.objects.filter(
        contract=contract, status=StockReservation.Status.ACTIVE,
    ).delete()
    # B5: pul to'langan shartnomaning broni muddatsiz — muddat o'tdi deb
    # bo'shatib bo'lmaydi (chernovik/tasdiq bosqichlarida esa muddat ishlaydi)
    paid = contract.status == Contract.Status.ACTIVE
    for product, quantity in _contract_needs(contract, warehouse).items():
        free = sellable_quantity(product, warehouse, for_contract=contract)
        take = min(quantity, max(free, 0))
        if take > 0:
            StockReservation.objects.create(
                product=product, warehouse=warehouse, quantity=take,
                kind=StockReservation.Kind.HARD, contract=contract,
                expires_at=(
                    None if paid
                    else _reservation_expiry(StockReservation.Kind.HARD)
                ),
            )


def sync_configuration_reservations(configuration):
    """Konfiguratsiyaning yumshoq bronini `required_from_stock` ga moslab quradi.

    Chernovik ombordan olinadigan narsani "Rejada" deb belgilaydi — bu hech
    kimni to'smaydi, faqat boshqa engineer va salesga xavfni ko'rsatadi.
    3-to'plam §1: modify'da bazaviy modelning O'ZI va faqat qo'shilgan
    qatorlar band qilinadi — mashina ichidagi o'zgarmagan qismlar emas.
    """
    from apps.configurator.models import Configuration
    from apps.inventory.models import StockReservation

    # Yumshoq bron chernovikdan to texnik tasdiqgacha turadi — finalize'da
    # shartnomaning qattiq broni o'rnini egallaydi
    held_statuses = {
        Configuration.Status.DRAFT,
        # 9-to'plam §1: aniqlashtirish kutilayotganda ish (va bron) joyida
        Configuration.Status.PENDING_CLARIFICATION,
        Configuration.Status.PENDING_SALES,
        Configuration.Status.APPROVED,
    }
    if configuration.status not in held_statuses:
        release_reservations(configuration=configuration)
        return

    # YANGI-OQIM B5.2: boshlang'ich to'lov kelgan zanjirda bron endi "reja"
    # emas — QATTIQ va muddatsiz (pul to'langan molni muddat o'tdi deb
    # bo'shatib bo'lmaydi). Ungacha — yumshoq, muddati bilan.
    kind = StockReservation.Kind.SOFT
    expires_at = _reservation_expiry(kind)
    if configuration.is_paid:
        kind = StockReservation.Kind.HARD
        expires_at = None

    warehouse = configuration.warehouse or main_warehouse()
    StockReservation.objects.filter(
        configuration=configuration, status=StockReservation.Status.ACTIVE,
    ).delete()
    for product, quantity in configuration.required_from_stock:
        room = plannable_quantity(product, warehouse, for_configuration=configuration)
        take = min(quantity, max(room, 0))
        if take > 0:
            StockReservation.objects.create(
                product=product, warehouse=warehouse, quantity=take,
                kind=kind, configuration=configuration,
                expires_at=expires_at,
            )


def mark_reservations_shipped(contract):
    """To'lov tasdiqlandi — bron chiqimga aylandi."""
    from apps.inventory.models import StockReservation

    release_reservations(
        contract=contract, status=StockReservation.Status.SHIPPED,
    )


def update_cost_price(product, unit_price):
    """Kirimdan keyin mahsulot tannarxini yangilaydi — oxirgi xarid narxi.

    Narx QQS'siz sof xarid narxi (qator `unit_price`). 0 yoki manfiy kelsa
    mavjud tannarx buzilmaydi. Shu tufayli kirimdan keyin `stock_price`
    0 bo'lib qolmaydi va configurator qatori `needs_price` da qulflanmaydi.
    """
    from decimal import Decimal

    price = Decimal(unit_price or 0)
    if price <= 0 or product.cost_price == price:
        return
    product.cost_price = price
    product.save(update_fields=['cost_price'])


def configuration_signature(base_product_id, items):
    """Konfiguratsiya tarkibining takrorlanmas imzosi.

    Bir xil bazaviy model + bir xil butlovchilar (miqdori bilan) doim
    bir xil imzo beradi — shu orqali "bunday variant avval bo'lganmi"
    degan taqqoslash bajariladi (TZ 6.2).
    """
    from hashlib import sha256

    parts = sorted(f'{component_id}x{int(quantity)}' for component_id, quantity in items)
    raw = f'{base_product_id}|' + '|'.join(parts)
    return sha256(raw.encode('utf-8')).hexdigest()[:40]


def create_product_from_order(*, name, sku='', kind=None, cost_price=0):
    """Buyurtma qilingan yangi mahsulotni katalogga qo'shadi (TZ 7).

    Buyurtmachi to'ldirish hisobiga hali bazada yo'q tovarni yozganda,
    o'sha tovar shu yerda mahsulot sifatida yaratiladi. Alohida "mahsulot
    qo'shish" oynasi yo'q — buyurtma qilishning o'zi mahsulot qo'shishdir.
    """
    from apps.core.utils import next_number
    from apps.inventory.models import Product

    name = (name or '').strip()
    sku = (sku or '').strip()
    if not name and not sku:
        raise ValueError('Mahsulot nomi yoki SKU kerak.')

    existing = None
    if sku:
        existing = Product.objects.filter(sku=sku).first()
    if not existing and name:
        existing = Product.objects.filter(name__iexact=name).first()
    if existing:
        return existing

    return Product.objects.create(
        sku=sku or next_number(Product, 'MAH'),
        name=name or sku,
        kind=kind or Product.Kind.COMPONENT,
        cost_price=cost_price or 0,
    )
