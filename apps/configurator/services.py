from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

HEADERS = [
    'Butlovchi',
    'Belgi',
    'Miqdor',
    'Narx',
    'Summa',
    'Omborda',
    'Yetishmaydi',
    'Manba',
]


def build_configuration_workbook(configuration):
    """Configurator natijasini Excel chernovigiga aylantiradi."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Configurator'

    act_number = configuration.act.number if configuration.act else '-'
    sheet.append([f'Konfiguratsiya: {configuration.number}'])
    sheet.append([f'Bazaviy model: {configuration.base_product}'])
    sheet.append([f'Mijoz: {configuration.client or "-"}'])
    sheet.append([f'ACT: {act_number}'])
    sheet.append([f'Holat: {configuration.get_status_display()}'])
    sheet.append([])
    sheet.append(HEADERS)

    header_row = sheet.max_row
    for cell in sheet[header_row]:
        cell.font = Font(bold=True)

    for item in configuration.items.select_related('component'):
        sheet.append([
            item.component.name,
            item.label,
            item.quantity,
            float(item.unit_price),
            float(item.subtotal),
            float(item.available),
            float(item.shortage),
            'Ombordan' if item.source == 'stock' else 'Kirim qilinadi',
        ])

    sheet.append([])
    sheet.append(['', '', '', 'Jami:', float(configuration.total_price)])
    sheet.cell(row=sheet.max_row, column=4).font = Font(bold=True)
    sheet.cell(row=sheet.max_row, column=5).font = Font(bold=True)

    for index in range(1, len(HEADERS) + 1):
        sheet.column_dimensions[get_column_letter(index)].width = 18

    return workbook


def resolve_variant(configuration):
    """Konfiguratsiya uchun tayyor variantni topadi yoki yangisini yaratadi.

    TZ 6.2: bir xil tarkib avval bo'lgan bo'lsa — ombordagi tayyor pozitsiya
    va uning narxi ishlatiladi; bo'lmasa yangi variant omborga qo'shiladi va
    keyingi safar qayta ishlatiladi.
    """
    from django.db.transaction import atomic

    from apps.inventory.models import Product, ProductSpec

    existing = configuration.matching_variant
    if existing:
        return existing, False

    base = configuration.base_product
    with atomic():
        index = Product.objects.filter(base_model=base).count() + 1
        variant = Product.objects.create(
            sku=f'{base.sku}-V{index:02d}',
            name=f'{base.name} ({configuration.number})',
            kind=base.kind,
            description=f'{base.name} bazasida yig\'ilgan konfiguratsiya',
            cost_price=configuration.items_total,
            sale_price=configuration.items_total,
            base_model=base,
            signature=configuration.signature,
        )
        for item in configuration.items.select_related('component'):
            ProductSpec.objects.create(
                product=variant,
                component=item.component,
                label=item.label,
                quantity=item.quantity,
            )
    return variant, True


def _configuration_owner_sales(configuration):
    """Konfiguratsiya ortidagi zayavka egasi (sales) — tasdiq va xabarlar unga."""
    request_obj = (
        configuration.requests.filter(created_by__isnull=False)
        .order_by('-created_at').first()
    )
    return request_obj.created_by if request_obj else None


def submit_configuration(configuration, user):
    """Engineer texnik yechimni sales ko'rigiga yuboradi (TOPSHIRIQ-2 #4).

    Sales mijozga ko'rsatadi: o'zgartirish kerak bo'lsa izoh bilan
    qaytaradi, ma'qul bo'lsa tasdiqlaydi — shundan keyingina ta'minot
    va yig'ish boshlanadi.
    """
    from rest_framework.exceptions import PermissionDenied, ValidationError

    from apps.accounts.models import User
    from apps.configurator.models import Configuration
    from apps.core.models import Notification

    if not (user.is_admin or user.is_engineer):
        raise PermissionDenied('Texnik yechimni Engineer yuboradi.')
    if configuration.status != Configuration.Status.DRAFT:
        raise ValidationError({'detail': 'Faqat chernovik ko\'rikka yuboriladi.'})
    if not configuration.items.exists():
        raise ValidationError({'detail': 'Konfiguratsiya qatorlari kiritilmagan.'})

    configuration.status = Configuration.Status.PENDING_SALES
    configuration.save()

    owner = _configuration_owner_sales(configuration)
    recipients = [owner] if owner else list(
        User.objects.filter(role=User.Role.SALES, is_active=True)
    )
    for recipient in recipients:
        Notification.objects.create(
            user=recipient,
            title=f'{configuration.number}: konfiguratsiyani ko\'rib chiqing',
            message=(
                'Engineer texnik yechimni tayyorladi — mijozga ko\'rsatib '
                'tasdiqlang yoki izoh bilan qaytaring.'
            ),
            level=Notification.Level.WARNING,
            entity='Configuration',
            object_id=str(configuration.pk),
        )
    return configuration


def _decide_configuration(configuration, user, decision, comment):
    from rest_framework.exceptions import PermissionDenied, ValidationError

    from apps.configurator.models import Configuration, ConfigurationApproval

    if not (user.is_admin or user.is_sales):
        raise PermissionDenied('Texnik yechimni sales (yoki admin) tasdiqlaydi.')
    if configuration.status != Configuration.Status.PENDING_SALES:
        raise ValidationError({'detail': 'Konfiguratsiya sales ko\'rigida emas.'})
    ConfigurationApproval.objects.create(
        configuration=configuration,
        decision=decision,
        comment=comment,
        decided_by=user,
    )


def approve_configuration(configuration, user, comment=''):
    """Sales texnik yechimni tasdiqlaydi — endi ta'minot/yig'ish mumkin."""
    from apps.configurator.models import Configuration, ConfigurationApproval, ConfigurationRequest
    from apps.core.models import Notification

    _decide_configuration(
        configuration, user, ConfigurationApproval.Decision.APPROVED, comment,
    )
    configuration.status = Configuration.Status.APPROVED
    configuration.save()
    # Zayavka holati ergashadi: texnik yechim qabul qilindi
    configuration.requests.filter(
        status=ConfigurationRequest.Status.IN_PROGRESS,
    ).update(status=ConfigurationRequest.Status.DONE)

    if configuration.created_by:
        Notification.objects.create(
            user=configuration.created_by,
            title=f'{configuration.number}: texnik yechim tasdiqlandi',
            message=(
                'Sales mijoz bilan kelishdi. Yetishmagani bo\'lsa buyurtmachiga '
                'yuboring, mol to\'liq bo\'lgach yig\'ib yakunlang.'
            ),
            level=Notification.Level.INFO,
            entity='Configuration',
            object_id=str(configuration.pk),
        )
    return configuration


def reject_configuration(configuration, user, comment=''):
    """Sales izoh bilan qaytaradi — engineer nimani o'zgartirishni biladi."""
    from apps.configurator.models import Configuration, ConfigurationApproval
    from apps.core.models import Notification

    _decide_configuration(
        configuration, user, ConfigurationApproval.Decision.REJECTED, comment,
    )
    configuration.status = Configuration.Status.DRAFT
    configuration.save()

    if configuration.created_by:
        Notification.objects.create(
            user=configuration.created_by,
            title=f'{configuration.number}: konfiguratsiya qaytarildi',
            message=comment or 'Sales o\'zgartirish so\'radi.',
            level=Notification.Level.WARNING,
            entity='Configuration',
            object_id=str(configuration.pk),
        )
    return configuration


def act_suggestion_text(configuration):
    """ACT uchun tayyor matn — bajarilgan ish `changes` dan yoziladi (#4D)."""
    quantity = getattr(configuration, 'quantity', 1)
    lines = [f'{quantity} ta {configuration.base_product.name} olindi.']
    changes = configuration.changes
    for row in changes['removed']:
        lines.append(
            f"{row['component'].name} chiqarilib omborga qaytarildi "
            f"({row['quantity'] * quantity} dona)."
        )
    for row in changes['added']:
        lines.append(
            f"O'rniga {row['component'].name} o'rnatildi "
            f"({row['quantity'] * quantity} dona)."
        )
    return ' '.join(lines)


def assemble_configuration(configuration, user, *, removals=None, strict=True):
    """Yig'ish — alohida qadam (TOPSHIRIQ-2 #4): faqat tasdiqlangan yechim.

    build: variant topiladi/yaratiladi va butlovchilardan yig'iladi;
    modify: tayyor mahsulot fizik o'zgartiriladi (ombor harakatlari,
    bugalterga ACT xabari). Muvaffaqiyatda `assembled_at` yoziladi —
    `finalize` shusiz o'tmaydi.
    """
    from django.utils.timezone import now

    from rest_framework.exceptions import PermissionDenied, ValidationError

    from apps.configurator.models import Configuration

    if not (user.is_admin or user.is_engineer):
        raise PermissionDenied('Yig\'ishni Engineer bajaradi.')
    if configuration.status != Configuration.Status.APPROVED:
        raise ValidationError({
            'detail': 'Avval texnik yechim sales tomonidan tasdiqlanishi kerak.',
        })
    if configuration.assembled_at:
        return True, []

    if configuration.mode == Configuration.Mode.MODIFY:
        variant, _ = finalize_modification(configuration, user, removals)
        configuration.variant = variant
        assembled, missing = True, []
    else:
        variant, _ = resolve_variant(configuration)
        configuration.variant = variant
        configuration.save(update_fields=['variant'])
        assembled, missing = assemble_variant(configuration, user, strict=strict)
        # Variant allaqachon omborda yetarli bo'lsa ham "yig'ilgan" hisoblanadi
        from apps.inventory.services import available_quantity

        if not assembled and not missing and available_quantity(
            variant, configuration.warehouse,
        ) >= configuration.quantity:
            assembled = True

    if assembled:
        configuration.assembled_at = now()
    configuration.save()
    return assembled, missing


def assemble_variant(configuration, user, *, strict=True):
    """Build rejimida jismoniy yig'ish (§10.1): butlovchilar chiqadi, variant kiradi.

    Avval bu qadam umuman yo'q edi: variant katalogda yaratilardi-yu, ombor
    qoldig'i 0 bo'lib qolar, shartnoma to'lovi hech qachon o'tmas edi.

    Variant omborda allaqachon bor bo'lsa (>= 1) yig'ilmaydi — sotuv tayyor
    qoldiqdan ketadi. Butlovchi yetmasa: strict=True — 400 (nomlar bilan,
    narxsiz — engineer pul ko'rmaydi), strict=False — (False, nomlar) qaytadi
    va jarayon davom etadi (mol TLD orqali kelgach yig'iladi).
    """
    from django.db.transaction import atomic
    from rest_framework.exceptions import ValidationError

    from apps.inventory.models import StockMovement
    from apps.inventory.services import (
        apply_movement,
        available_quantity,
        main_warehouse,
        sellable_quantity,
    )

    variant = configuration.variant
    if variant is None:
        if strict:
            raise ValidationError({'detail': 'Avval konfiguratsiyani yakunlang.'})
        return False, []

    warehouse = configuration.warehouse or main_warehouse()
    batch = configuration.quantity
    if available_quantity(variant, warehouse) >= batch:
        return False, []

    # §11.4: boshqa shartnomalarga band qilingan butlovchi yig'ishga olinmaydi;
    # shu konfiguratsiyaning o'z shartnomasi band qilgani esa ochiq
    own_contract = (
        configuration.contracts
        .exclude(status__in=['rejected', 'cancelled'])
        .order_by('-id')
        .first()
    )
    # #3: butun partiya uchun tekshiriladi — qator miqdori × partiya
    missing = [
        item.component.name
        for item in configuration.items.select_related('component')
        if sellable_quantity(
            item.component, warehouse, for_contract=own_contract,
        ) < item.quantity * batch
    ]
    if missing:
        if strict:
            raise ValidationError({
                'detail': "Yig'ish uchun butlovchilar omborda yetarli emas.",
                'items': missing,
            })
        return False, missing

    with atomic():
        for item in configuration.items.select_related('component'):
            apply_movement(
                product=item.component, warehouse=warehouse,
                type=StockMovement.Type.OUT, quantity=item.quantity * batch,
                reason=StockMovement.Reason.CONFIGURATION,
                reference=configuration.number, user=user,
            )
        apply_movement(
            product=variant, warehouse=warehouse,
            type=StockMovement.Type.IN, quantity=batch,
            reason=StockMovement.Reason.CONFIGURATION,
            reference=configuration.number, user=user,
        )
    return True, []


def finalize_modification(configuration, user, removal_overrides=None):
    """Tayyor mahsulotni o'zgartirishni yakunlaydi (modify rejimi, TZ 6.2).

    Ombor harakatlari:
      - butun bazaviy mahsulotdan 1 dona chiqim;
      - qo'shilgan butlovchilar ombordan chiqim;
      - yechib olinganlar omborga kirim (narxi bilan yozib qo'yiladi);
      - o'zgartirilgan mahsulot (variant) omborga 1 dona kirim.

    removal_overrides: {component_id: narx} — yechib olingan qism narxini
    o'zgartirish imkoniyati. Yakunda bugalterga xabar boradi.
    """
    from decimal import Decimal

    from django.db.transaction import atomic
    from rest_framework.exceptions import ValidationError

    from apps.core.models import Notification
    from apps.configurator.models import ConfigurationRemoval
    from apps.inventory.models import StockMovement
    from apps.inventory.services import apply_movement, available_quantity

    warehouse = configuration.warehouse
    if warehouse is None:
        # Biznesda bitta ombor bor — tanlanmagan bo'lsa yagona ombor olinadi
        from apps.inventory.services import main_warehouse

        warehouse = main_warehouse()
        configuration.warehouse = warehouse

    base = configuration.base_product
    batch = configuration.quantity  # #3: butun partiya birdek o'zgartiriladi

    # 3-to'plam §1: qo'riqchi yagona ta'rifdan o'qiydi — model × partiya va
    # qo'shilgan qatorlar × partiya. O'zgarmagan qismlar tekshirilmaydi:
    # ular tayyor mashinaning ichida keladi, omborga aloqasi yo'q.
    shortages = [
        f'{product.name} (kerak: {needed}, '
        f'omborda: {available_quantity(product, warehouse)})'
        for product, needed in configuration.required_from_stock
        if available_quantity(product, warehouse) < needed
    ]
    if shortages:
        raise ValidationError({
            'detail': (
                "O'zgartirish uchun omborda yetarli emas — avval "
                'yetishmaganini buyurtmachidan kirim qiling.'
            ),
            'items': shortages,
        })

    changes = configuration.changes

    overrides = {int(k): Decimal(str(v)) for k, v in (removal_overrides or {}).items()}

    with atomic():
        variant, created = resolve_variant(configuration)

        # butun partiya ishga olinadi
        apply_movement(
            product=base, warehouse=warehouse,
            type=StockMovement.Type.OUT, quantity=batch,
            reason=StockMovement.Reason.CONFIGURATION,
            reference=configuration.number, user=user,
        )
        # qo'shilgan butlovchilar ombordan
        for row in changes['added']:
            apply_movement(
                product=row['component'], warehouse=warehouse,
                type=StockMovement.Type.OUT, quantity=row['quantity'] * batch,
                reason=StockMovement.Reason.CONFIGURATION,
                reference=configuration.number, user=user,
            )
        # yechib olinganlar omborga qaytadi — narxi (bitta donaga) yozib qo'yiladi
        removed_lines = []
        for row in changes['removed']:
            price = overrides.get(row['component'].pk, row['unit_price'])
            ConfigurationRemoval.objects.create(
                configuration=configuration,
                component=row['component'],
                quantity=row['quantity'] * batch,
                unit_price=price,
                note='Tayyor mahsulotdan yechib olindi',
            )
            apply_movement(
                product=row['component'], warehouse=warehouse,
                type=StockMovement.Type.IN, quantity=row['quantity'] * batch,
                reason=StockMovement.Reason.CONFIGURATION,
                reference=configuration.number, user=user,
            )
            removed_lines.append(
                f"{row['component'].name} x{row['quantity'] * batch} — {price}",
            )

        # o'zgartirilgan mahsulot tayyor pozitsiya sifatida omborga kiradi
        apply_movement(
            product=variant, warehouse=warehouse,
            type=StockMovement.Type.IN, quantity=batch,
            reason=StockMovement.Reason.CONFIGURATION,
            reference=configuration.number, user=user,
        )

        # TZ: yechib olinganini ACT qilib bugalterga jo'natamiz — faqat unga
        # (user'siz xabar hammaga ko'rinardi, ACT tafsiloti esa pul ma'lumoti)
        from apps.accounts.models import User

        act_number = configuration.act.number if configuration.act else '-'
        for bugalter in User.objects.filter(role=User.Role.BUGALTER, is_active=True):
            Notification.objects.create(
                user=bugalter,
                title=f'{configuration.number}: tarkib o\'zgartirildi (ACT {act_number})',
                message=(
                    'Yechib olindi va omborga qaytdi: ' + '; '.join(removed_lines)
                    if removed_lines else 'Tarkibga faqat qo\'shimcha kiritildi.'
                ),
                level=Notification.Level.INFO,
                entity='Configuration',
                object_id=str(configuration.pk),
            )

    return variant, created


def copy_factory_spec(configuration):
    """Zavod tarkibini konfiguratsiya qatorlariga ko'chiradi (TZ 6.1).

    Model tanlanganda uning ichidagi barcha narsa tayyor keladi — keyin
    kerakli qatorlar o'zgartiriladi. Serializer ham, take_request ham
    aynan shu funksiyani chaqiradi (mantiq bitta joyda turadi).
    """
    from apps.configurator.models import ConfigurationItem

    for spec in configuration.base_product.specs.select_related('component'):
        ConfigurationItem.objects.create(
            configuration=configuration,
            component=spec.component,
            label=spec.label,
            quantity=spec.quantity,
        )


def take_request(request_obj, user, base_product=None, warehouse=None, mode=None):
    """Engineer zayavkani ishga oladi — chernovik konfiguratsiya avtomatik ochiladi.

    Bazaviy model: so'rov tanasidagi `base_product` > zayavkada yozilgani.
    Ikkalasi ham bo'lmasa 400 — konfiguratsiya modelsiz yaratilmaydi.
    """
    from django.db.transaction import atomic
    from rest_framework.exceptions import PermissionDenied, ValidationError

    from apps.configurator.models import Configuration, ConfigurationRequest
    from apps.inventory.models import Product

    if not (user.is_admin or user.is_engineer):
        raise PermissionDenied('Zayavkani faqat Engineer ishga oladi.')
    if request_obj.status != ConfigurationRequest.Status.NEW:
        raise ValidationError('Faqat yangi zayavkani ishga olish mumkin.')

    base_product = base_product or request_obj.base_product
    if base_product is None:
        raise ValidationError({
            'base_product': "Konfiguratsiya ochish uchun bazaviy model tanlanishi shart.",
        })
    if base_product.kind != Product.Kind.MACHINE:
        raise ValidationError({'base_product': 'Faqat tayyor model tanlanadi.'})

    from apps.inventory.services import main_warehouse

    with atomic():
        configuration = Configuration.objects.create(
            base_product=base_product,
            client=request_obj.client,
            warehouse=warehouse or request_obj.warehouse or main_warehouse(),
            mode=mode or Configuration.Mode.BUILD,
            # #3: mijoz nechta so'ragani zayavkadan ko'chadi (engineer
            # chernovikda o'zgartira oladi)
            quantity=request_obj.quantity,
            note=f'{request_obj.number}: {request_obj.text}',
            created_by=user,
        )
        copy_factory_spec(configuration)

        # §11.4: chernovik butlovchilarni "Rejada" deb belgilaydi (yumshoq bron)
        from apps.inventory.services import sync_configuration_reservations

        sync_configuration_reservations(configuration)

        request_obj.status = ConfigurationRequest.Status.IN_PROGRESS
        request_obj.taken_by = user
        request_obj.configuration = configuration
        request_obj.save()

    return request_obj


def send_missing_to_procurement(configuration, user):
    """Konfiguratsiyadagi omborda yo'q butlovchilarni buyurtmachiga yuboradi.

    Yetishmayotgan qatorlardan to'ldirish hisobi (chernovik, TLD-) ochiladi va
    konfiguratsiyaga bog'lanadi. Buyurtmachi, sales va bugalterga xabar boradi.
    Keyingi zanjir — TZ 7: buyurtmachi yuboradi -> bugalter tekshiradi ->
    admin tasdiqlaydi -> bugalter to'laydi -> kirim (timeline bilan kuzatiladi).
    """
    from django.db.transaction import atomic
    from rest_framework.exceptions import PermissionDenied, ValidationError

    from apps.accounts.models import User
    from apps.configurator.models import Configuration
    from apps.core.models import Notification
    from apps.inventory.services import main_warehouse
    from apps.procurement.models import Replenishment, ReplenishmentItem

    if not (user.is_admin or user.is_engineer):
        raise PermissionDenied('Buyurtmachiga yuborishni Engineer bajaradi.')

    # TOPSHIRIQ-2 #4: ta'minot faqat TASDIQLANGAN yechim uchun ishlaydi —
    # aks holda mijoz ko'rmagan tarkib uchun mol olinib, pul to'lanardi
    if configuration.status != Configuration.Status.APPROVED:
        raise ValidationError({
            'detail': (
                'Avval texnik yechim sales tomonidan tasdiqlansin '
                '(submit -> sales approve) — keyin buyurtmachiga yuboriladi.'
            ),
        })

    # Bitta konfiguratsiya uchun bitta ochiq hisob: tugma ikki marta bosilsa
    # ikkinchi TLD ochilmaydi — front mavjudini `procurement` maydonidan ko'radi
    existing = configuration.open_replenishment
    if existing:
        raise ValidationError({
            'detail': (
                f'{configuration.number} uchun {existing.number} hisobi allaqachon '
                f'ochilgan ({existing.get_status_display()}) — yangisini ochish shart emas.'
            ),
            'replenishment': existing.pk,
        })

    # 3-to'plam §1: ro'yxat `required_from_stock` dan — modify'da yetishmagan
    # BAZAVIY MODEL ham TLD ga tushadi, o'zgarmagan qismlar esa tushmaydi
    missing = configuration.missing_items
    if not missing:
        raise ValidationError({
            'detail': "Hammasi omborda yetarli — buyurtmachiga yuborish shart emas.",
        })

    # §4.3 (SIDEBAR-VA-EGALIK): zayavka egasi (sales) bir marta topilib hisobga
    # yozib qo'yiladi — bildirishnoma va pending_sales bosqichi shu odamniki
    owner_request = (
        configuration.requests
        .filter(created_by__isnull=False)
        .order_by('-created_at')
        .first()
    )
    owner_sales = owner_request.created_by if owner_request else None

    with atomic():
        replenishment = Replenishment.objects.create(
            warehouse=configuration.warehouse or main_warehouse(),
            configuration=configuration,
            owner_sales=owner_sales,
            note=f"{configuration.number} uchun yetishmayotgan butlovchilar",
            created_by=user,
        )
        for row in missing:
            ReplenishmentItem.objects.create(
                replenishment=replenishment,
                product=row['product'],
                quantity=row['shortage'],
                unit_price=row['product'].cost_price or 0,
                note=f'{configuration.number} konfiguratsiyasi uchun',
            )

    # Hovuz: buyurtmachi (ish unga keldi) va bugalter (oldindan biladi).
    # Sales — hovuz EMAS (§4.2): faqat zayavka egasi; egasi aniqlanmasa
    # (ZVK'siz konfiguratsiya) barcha sales'ga tushadi — xabar yo'qolmasin.
    names = ', '.join(row['product'].name for row in missing)
    messages = {
        User.Role.SUPPLIER: 'kirim qilish kerak — buyurtmani rasmiylashtirib yuboring.',
        User.Role.BUGALTER: "tekshirib chiqing — buyurtmachi yuborgach tasdiq sizdan boshlanadi.",
    }
    recipients = list(
        User.objects.filter(role__in=messages.keys(), is_active=True)
    )
    sales_message = 'kirim qilish kerak — mijoz buyurtmangiz shu kirimni kutadi.'
    if owner_sales:
        sales_recipients = [owner_sales]
    else:
        sales_recipients = list(
            User.objects.filter(role=User.Role.SALES, is_active=True)
        )
    for recipient in recipients + sales_recipients:
        Notification.objects.create(
            user=recipient,
            title=f"{configuration.number}: omborda yo'q butlovchilar ({replenishment.number})",
            message=f'{names} — {messages.get(recipient.role, sales_message)}',
            level=Notification.Level.WARNING,
            entity='Replenishment',
            object_id=str(replenishment.pk),
        )
    return replenishment


def notify_engineers_about_request(request_obj):
    """Yangi zayavka haqida barcha faol engineerlarga eslatma (3-xato tuzatmasi)."""
    from apps.accounts.models import User
    from apps.core.models import Notification

    engineers = User.objects.filter(role=User.Role.ENGINEER, is_active=True)
    for engineer in engineers:
        Notification.objects.create(
            user=engineer,
            title=f'{request_obj.number}: yangi zayavka',
            message=(request_obj.text or '')[:500],
            level=Notification.Level.INFO,
            entity='ConfigurationRequest',
            object_id=str(request_obj.pk),
        )
