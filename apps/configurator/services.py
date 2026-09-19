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

    # YANGI-OQIM B2: shartnoma endi sales tasdig'ida ochiladi va summasi shu
    # narxlardan yig'iladi — narxsiz qator ko'rikka o'tmaydi. Buyurtmachi
    # narxni keyin kiritgan bo'lishi mumkin: nol qatorlar avval ombordan
    # qayta o'qiladi (save() narxni o'zi to'ldiradi), keyin tekshiriladi.
    for item in configuration.items.filter(unit_price=0):
        item.save()
    no_price = configuration.items_without_price
    if no_price:
        raise ValidationError({
            'detail': (
                "Narxsiz qator bilan ko'rikka yuborilmaydi — avval buyurtmachidan "
                'narx so\'rang (request-prices).'
            ),
            'items': [item.component.name for item in no_price],
        })

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


def request_prices(configuration, user):
    """Narxsiz qatorlar uchun buyurtmachidan narx so'raydi (YANGI-OQIM B2).

    Bu TLD EMAS: hech narsa buyurtma qilinmaydi, pul to'lanmaydi — buyurtmachi
    shunchaki tannarxni mahsulot kartasida kiritib beradi (§6-B ustamasi bilan
    sotuv narxiga aylanadi). §2.1 aylanmasi bir necha bor aylanishi mumkin,
    shuning uchun bu amal necha marta ham chaqiriladi; takrorida buyurtmachining
    eski o'qilmagan eslatmasi yangilanadi — yangisi qo'shilmaydi.
    """
    from rest_framework.exceptions import PermissionDenied, ValidationError

    from apps.accounts.models import User
    from apps.configurator.models import Configuration
    from apps.core.models import Notification

    if not (user.is_admin or user.is_engineer):
        raise PermissionDenied('Narx so\'rovini Engineer yuboradi.')
    # 10-to'plam §2: narx so'rovi faqat hali shartnomaga kirmagan bosqichlarda
    if configuration.status not in {
        Configuration.Status.DRAFT,
        Configuration.Status.PENDING_CLARIFICATION,
        Configuration.Status.PENDING_SALES,
    }:
        raise ValidationError({
            'detail': (
                'Bu bosqichda narx so\'ralmaydi — narx allaqachon '
                'shartnomaga kirib bo\'lgan.'
            ),
        })

    # Buyurtmachi allaqachon kiritgan narxlar nol qatorlarga tushsin
    for item in configuration.items.filter(unit_price=0):
        item.save()
    no_price = configuration.items_without_price
    if not no_price:
        raise ValidationError({
            'detail': 'Barcha qatorlarda narx bor — so\'rov shart emas.',
        })

    # 10-to'plam §1: eslatma MAHSULOTGA ishora qiladi — buyurtmachi
    # konfiguratsiyani ko'ra olmaydi (404 edi), mahsulot kartasi esa ochiq
    # va tannarx maydoni unda. Har bir narxsiz mahsulotga alohida eslatma:
    # vazifa ham alohida (beshta narx — beshta ish), yopilishi ham aniq
    # (price_arrived o'sha mahsulotnikini yopadi). Takror bosishda o'qilmagan
    # eslatma yangilanadi — kalit (user, Product, component).
    suppliers = list(
        User.objects.filter(role=User.Role.SUPPLIER, is_active=True)
    )
    for item in no_price:
        for supplier in suppliers:
            Notification.objects.update_or_create(
                user=supplier, entity='Product',
                object_id=str(item.component_id), is_read=False,
                defaults={
                    'title': f'{item.component.name}: tannarx kerak',
                    'message': (
                        f'{configuration.number} uchun so\'raldi. Bu buyurtma '
                        'emas — faqat tannarxni mahsulot kartasida kiriting.'
                    ),
                    'level': Notification.Level.WARNING,
                },
            )
    # B15: aylanma qadam tarixga tushadi
    from apps.configurator.models import ConfigurationRequestEvent

    names = ', '.join(item.component.name for item in no_price)
    log_request_event(
        configuration.requests.order_by('-created_at').first(),
        ConfigurationRequestEvent.Stage.PRICE_ASKED, user, names,
    )
    return [item.component.name for item in no_price]


def price_arrived(product, user):
    """Mahsulotga narx kiritildi — kutayotgan konfiguratsiyalar yangilanadi (B2.3).

    Nol narxli qatorlar to'ldiriladi; konfiguratsiyada narxsiz qator qolmasa
    buyurtmachining "narx kerak" eslatmasi yopiladi va narx SALES'GA qaytadi
    (engineerga emas — kelishuv shunday): sales mijoz bilan kelishadi.
    """
    from apps.accounts.models import User
    from apps.configurator.models import Configuration, ConfigurationItem
    from apps.core.models import Notification
    from apps.core.services import resolve_notifications

    if not product.stock_price:
        return

    suppliers = list(User.objects.filter(role=User.Role.SUPPLIER, is_active=True))
    # 10-to'plam §1: mahsulotga bog'langan "tannarx kerak" eslatmalari yopiladi
    for supplier in suppliers:
        resolve_notifications('Product', product.pk, user=supplier)

    waiting = (
        Configuration.objects
        .filter(
            status__in=[
                Configuration.Status.DRAFT,
                # 10-to'plam §2: aniqlashtirish kutilayotganda ham narx tushadi
                Configuration.Status.PENDING_CLARIFICATION,
                Configuration.Status.PENDING_SALES,
            ],
            items__component=product, items__unit_price=0,
        )
        .distinct()
    )
    for configuration in waiting:
        for item in ConfigurationItem.objects.filter(
            configuration=configuration, component=product, unit_price=0,
        ):
            item.save()  # save() ombor narxini o'zi to'ldiradi
        if configuration.items_without_price:
            continue  # hali boshqa narxsiz qatorlar bor — so'rov ochiq turadi
        for supplier in suppliers:
            resolve_notifications(
                'Configuration', configuration.pk, user=supplier,
            )
        owner = _configuration_owner_sales(configuration)
        if owner:
            Notification.objects.create(
                user=owner,
                title=f'{configuration.number}: narx keldi',
                message=(
                    'Buyurtmachi narxni kiritdi — mijoz bilan kelishing. '
                    'Ma\'qul bo\'lsa engineer ko\'rikka yuboradi.'
                ),
                level=Notification.Level.INFO,
                entity='Configuration',
                object_id=str(configuration.pk),
            )
        from apps.configurator.models import ConfigurationRequestEvent

        log_request_event(
            configuration.requests.order_by('-created_at').first(),
            ConfigurationRequestEvent.Stage.PRICE_GIVEN, user, product.name,
        )


def ask_sales(configuration, user, comment):
    """Engineer yarim yo'lda sales'dan aniqlashtirish so'raydi (9-to'plam §1B).

    Bu zayavkani rad etish EMAS: konfiguratsiya, tarkib va bron joyida
    qoladi — unda soatlab ish bor. Sales javob berib qaytaradi va engineer
    o'sha yerdan davom etadi. `reject_configuration`ning oynadagi aksi.
    """
    from rest_framework.exceptions import PermissionDenied, ValidationError

    from apps.accounts.models import User
    from apps.configurator.models import Configuration, ConfigurationApproval
    from apps.core.models import Notification

    if not (user.is_admin or user.is_engineer):
        raise PermissionDenied('Aniqlashtirishni Engineer so\'raydi.')
    if configuration.status != Configuration.Status.DRAFT:
        raise ValidationError({
            'detail': 'Aniqlashtirish faqat chernovik ustida so\'raladi.',
        })
    if not (comment or '').strip():
        raise ValidationError({
            'comment': 'Savol matni majburiy — sales nimaga javob berishni bilsin.',
        })

    configuration.status = Configuration.Status.PENDING_CLARIFICATION
    configuration.save()
    ConfigurationApproval.objects.create(
        configuration=configuration,
        step=ConfigurationApproval.Step.ENGINEER,
        decision=ConfigurationApproval.Decision.QUESTION,
        comment=comment,
        decided_by=user,
    )

    owner = _configuration_owner_sales(configuration)
    recipients = [owner] if owner else list(
        User.objects.filter(role=User.Role.SALES, is_active=True)
    )
    for recipient in recipients:
        Notification.objects.create(
            user=recipient,
            title=f'{configuration.number}: engineer savol berdi',
            message=comment,
            level=Notification.Level.WARNING,
            entity='Configuration',
            object_id=str(configuration.pk),
        )
    return configuration


def answer_clarification(configuration, user, comment):
    """Sales engineer savoliga javob beradi (9-to'plam §1B) — ish davom etadi."""
    from rest_framework.exceptions import PermissionDenied, ValidationError

    from apps.configurator.models import Configuration, ConfigurationApproval
    from apps.core.models import Notification
    from apps.core.services import resolve_notifications

    if not (user.is_admin or user.is_sales):
        raise PermissionDenied('Javobni sales (yoki admin) beradi.')
    if configuration.status != Configuration.Status.PENDING_CLARIFICATION:
        raise ValidationError({
            'detail': 'Konfiguratsiya sales javobini kutish bosqichida emas.',
        })
    if not (comment or '').strip():
        raise ValidationError({
            'comment': 'Javob matni majburiy — engineer davom eta olsin.',
        })

    configuration.status = Configuration.Status.DRAFT
    configuration.save()
    ConfigurationApproval.objects.create(
        configuration=configuration,
        step=ConfigurationApproval.Step.SALES,
        decision=ConfigurationApproval.Decision.ANSWER,
        comment=comment,
        decided_by=user,
    )
    # 4-to'plam §4: "javob bering" vazifasi bajarildi
    resolve_notifications('Configuration', configuration.pk, user=user)

    if configuration.created_by:
        Notification.objects.create(
            user=configuration.created_by,
            title=f'{configuration.number}: sales javob berdi',
            message=comment,
            level=Notification.Level.INFO,
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


def _configuration_client(configuration):
    """Zanjir mijozi: konfiguratsiyada, bo'lmasa zayavkada ko'rsatilgani."""
    if configuration.client_id:
        return configuration.client
    request_obj = (
        configuration.requests.filter(client__isnull=False)
        .order_by('-created_at').first()
    )
    return request_obj.client if request_obj else None


def approve_configuration(configuration, user, comment=''):
    """Sales texnik yechimni tasdiqlaydi — SHU YERDA shartnoma ochiladi (B1).

    YANGI OQIM: zanjir `CFG → SHT → pul → mol`. Tasdiq bilan draft shartnoma
    avtomatik ochiladi (egasi — zayavka sales'i), sales uni bugalterga
    yuboradi; ta'minot va yig'ish esa boshlang'ich to'lovdan keyin boshlanadi.
    """
    from apps.configurator.models import Configuration, ConfigurationApproval, ConfigurationRequest
    from apps.core.models import Notification
    from rest_framework.exceptions import ValidationError

    # B10: shartnoma — zanjirning majburiy bo'g'ini; mijozsiz ochilmaydi,
    # jimgina o'tkazib yuborilsa konfiguratsiya to'lov kutishda abadiy qotardi
    client = _configuration_client(configuration)
    if client is None:
        raise ValidationError({
            'detail': (
                'Zayavkada mijoz ko\'rsatilmagan — shartnoma ochib bo\'lmaydi. '
                'Avval zayavka yoki konfiguratsiyaga mijozni bog\'lang.'
            ),
        })

    _decide_configuration(
        configuration, user, ConfigurationApproval.Decision.APPROVED, comment,
    )
    configuration.status = Configuration.Status.APPROVED
    configuration.save()
    # 4-to'plam §4: "ko'rib chiqing" vazifasi bajarildi — salesniki yopiladi
    from apps.core.services import resolve_notifications

    resolve_notifications('Configuration', configuration.pk, user=user)
    # Zayavka holati ergashadi: texnik yechim qabul qilindi
    configuration.requests.filter(
        status=ConfigurationRequest.Status.IN_PROGRESS,
    ).update(status=ConfigurationRequest.Status.DONE)

    # B1: shartnoma zanjir boshida ochiladi (qaytadan tasdiqlashda mavjudi olinadi)
    if configuration.active_contract is None:
        from apps.sales.services import create_contract_from_configuration

        create_contract_from_configuration(configuration, user, client)

    contract = configuration.active_contract
    if configuration.created_by:
        Notification.objects.create(
            user=configuration.created_by,
            title=f'{configuration.number}: texnik yechim tasdiqlandi',
            message=(
                f'Sales mijoz bilan kelishdi — {contract.number} shartnomasi '
                'ochildi. Ta\'minot va yig\'ish boshlang\'ich to\'lovdan keyin '
                'boshlanadi.'
                if contract else 'Sales mijoz bilan kelishdi.'
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
    # 4-to'plam §4: qaror qabul qilindi — salesning eslatmasi yopiladi
    from apps.core.services import resolve_notifications

    resolve_notifications('Configuration', configuration.pk, user=user)

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


def change_quantity(configuration, user, *, quantity, comment='', via_request=False):
    """Partiya sonini o'zgartiradi (4-to'plam §2) — yon ta'sirlari bilan.

    Mijoz "10 emas, 100 kerak" desa zanjir qaytadan boshlanmaydi: son
    yangilanadi, bron yangi partiyaga moslashadi, zayavka soni ergashadi.
    Bu tijoriy o'zgarish — `approved` yechim sales ko'rigiga qaytadi
    (narx va muddat mijoz bilan qayta kelishiladi). Sales so'raydi,
    engineer yozadi — tarkib bilan ishlaydigan odam bitta (§3.4 egalik).
    """
    from rest_framework.exceptions import PermissionDenied, ValidationError

    from apps.configurator.models import Configuration
    from apps.core.models import Notification
    from apps.inventory.services import sync_configuration_reservations
    from apps.procurement.models import Replenishment

    # 6-to'plam §4: sonni BELGILAYDIGAN odam — sales (u mijoz bilan
    # kelishadi); engineer tarkib bilan ishlaydi, son bilan emas.
    # Zayavka orqali kelganda rol tekshiruvi zayavkaning o'zida bo'lgan.
    if not via_request and not (user.is_admin or user.is_sales):
        raise PermissionDenied(
            'Partiyani sales belgilaydi — u mijoz bilan kelishadi.',
        )

    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        raise ValidationError({'quantity': 'Partiya soni butun son bo\'lishi kerak.'})
    if quantity < 1:
        raise ValidationError({'quantity': 'Partiya kamida 1 dona bo\'ladi.'})

    allowed = {
        Configuration.Status.DRAFT,
        Configuration.Status.PENDING_SALES,
        Configuration.Status.APPROVED,
    }
    if configuration.status not in allowed:
        raise ValidationError({
            'detail': (
                f"'{configuration.get_status_display()}' holatida partiya "
                "o'zgartirilmaydi — shartnoma ochilgan yoki zanjir yopilgan."
            ),
        })
    if configuration.assembled_at:
        raise ValidationError({
            'detail': (
                "Mahsulot allaqachon yig'ilgan — ombor harakatlari yozilgan, "
                "partiya endi o'zgarmaydi."
            ),
        })
    # YANGI-OQIM B13: boshlang'ich to'lovdan keyin HECH NARSA o'zgarmaydi —
    # 10 taning puli olingan, 100 ta esa boshqa shartnoma
    if configuration.is_paid:
        raise ValidationError({
            'detail': (
                "Boshlang'ich to'lov qabul qilingan — partiya o'zgarmaydi. "
                "O'zgarish kerak bo'lsa alohida rasmiylashtiriladi."
            ),
        })

    # Ochiq TLD chernovikdan o'tgan bo'lsa — mol yo'lga chiqqan, partiyani
    # jimgina o'zgartirish mumkin emas. Chernovik TLD to'smaydi: buyurtmachi
    # qatorlarni baribir o'zi tahrirlaydi.
    open_tld = configuration.open_replenishment
    if open_tld and open_tld.status != Replenishment.Status.DRAFT:
        raise ValidationError({
            'detail': (
                f'{open_tld.number} hisobi "{open_tld.get_status_display()}" '
                "holatida — mol buyurtma qilingan yoki to'langan. Avval TLD "
                "bekor qilinsin yoki kirim qilinsin."
            ),
            'replenishment': open_tld.pk,
        })

    old_quantity = configuration.quantity
    if quantity == old_quantity:
        raise ValidationError({'quantity': 'Partiya soni o\'zgarmadi.'})

    was_approved = configuration.status == Configuration.Status.APPROVED
    configuration.quantity = quantity
    if was_approved:
        # Mijoz roziligi eskirdi: 10 taning narxi 100 taniki emas
        configuration.status = Configuration.Status.PENDING_SALES
    configuration.save()

    # Bron yangi partiyaga moslashadi (required_from_stock × yangi son)
    sync_configuration_reservations(configuration)
    # Zayavka soni ergashadi — ikki hujjatda ikki xil son qolmasin
    configuration.requests.update(quantity=quantity)

    # YANGI-OQIM B1 oqibati: shartnoma allaqachon ochilgan (pul hali yo'q —
    # draft/rejected) — qatordagi son va jami ham ergashadi
    from apps.sales.models import Contract

    contract = (
        configuration.contracts
        .exclude(status=Contract.Status.CANCELLED)
        .order_by('-id')
        .first()
    )
    if contract and contract.status in {
        Contract.Status.DRAFT, Contract.Status.REJECTED,
    }:
        contract.items.filter(product=configuration.base_product).update(
            quantity=quantity,
        )
        contract.total_amount = contract.items_total_with_vat
        contract.prepayment_percent = None  # foiz yangi summadan qayta olinadi
        contract.save()

    change_text = f'Partiya {old_quantity} dan {quantity} ga o\'zgardi.'
    if comment:
        change_text += f' Izoh: {comment}'

    owner = _configuration_owner_sales(configuration)
    if owner:
        Notification.objects.create(
            user=owner,
            title=f'{configuration.number}: partiya {old_quantity} → {quantity}',
            message=change_text + (
                ' Narx va muddatni mijoz bilan qayta tasdiqlang.'
                if was_approved else ''
            ),
            level=Notification.Level.WARNING if was_approved else Notification.Level.INFO,
            entity='Configuration',
            object_id=str(configuration.pk),
        )
    if open_tld:
        from apps.accounts.models import User

        for supplier in User.objects.filter(role=User.Role.SUPPLIER, is_active=True):
            Notification.objects.create(
                user=supplier,
                title=f'{open_tld.number}: partiya o\'zgardi',
                message=(
                    f'{configuration.number}: {change_text} Hisob qatorlarini '
                    'yangi songa moslab chiqing.'
                ),
                level=Notification.Level.WARNING,
                entity='Replenishment',
                object_id=str(open_tld.pk),
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


def _require_paid_chain(configuration):
    """YANGI-OQIM B4: ta'minot va yig'ish faqat boshlang'ich to'lovdan keyin.

    Zanjir endi `CFG → SHT → pul → mol`: pul kelmaguncha mol buyurtma
    qilinmaydi va yig'ilmaydi. Shartnoma rad etilgan/bekor qilingan bo'lsa —
    zanjir to'xtagan, boshqa matn bilan 400.
    """
    from rest_framework.exceptions import ValidationError

    from apps.sales.models import Contract

    contract = configuration.contracts.order_by('-id').first()
    if contract is None:
        raise ValidationError({
            'detail': (
                'Shartnoma ochilmagan — avval sales texnik yechimni tasdiqlasin '
                '(approve shartnomani o\'zi ochadi).'
            ),
        })
    if contract.status in {Contract.Status.REJECTED, Contract.Status.CANCELLED}:
        raise ValidationError({
            'detail': f'Shartnoma rad etildi — zanjir to\'xtadi ({contract.number}).',
            'contract': contract.pk,
        })
    if contract.status not in {Contract.Status.ACTIVE, Contract.Status.COMPLETED}:
        raise ValidationError({
            'detail': f"Boshlang'ich to'lov kutilmoqda — {contract.number}.",
            'contract': contract.pk,
        })
    return contract


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
    # B4: yig'ish — pul kelgandan keyingi qadam (13–16 qulfi)
    _require_paid_chain(configuration)
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
        # 4-to'plam §4: "yig'ing" vazifasi bajarildi — engineerniki yopiladi
        from apps.core.services import resolve_notifications

        resolve_notifications('Configuration', configuration.pk, user=user)
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
            item.component, warehouse,
            for_contract=own_contract,
            # B5: to'lovdan keyin o'z broni QATTIQ — yig'ishda o'ziga ochiq
            for_configuration=configuration,
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
        # B15: zayavka tarixi — roadmap (B8) aylanma qadamlarni shundan o'qiydi
        from apps.configurator.models import ConfigurationRequestEvent

        log_request_event(request_obj, ConfigurationRequestEvent.Stage.TAKEN, user)

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
    # B4: ta'minot ham pul kelgandan keyingi qadam — mol pulga bog'lanadi
    _require_paid_chain(configuration)

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


def log_request_event(request_obj, stage, user=None, comment=''):
    """Zayavka tarixiga qadam yozadi (B15) — aylanma faqat shu yerda iz qoldiradi."""
    from apps.configurator.models import ConfigurationRequestEvent

    if request_obj is None:
        return None
    return ConfigurationRequestEvent.objects.create(
        request=request_obj, stage=stage, comment=comment, created_by=user,
    )


def reject_request(request_obj, user, comment):
    """Engineer YANGI zayavkani izoh bilan sales'ga qaytaradi (B15, 9-§1A).

    Faqat A holati: engineer ochib ko'rdi, hali ishga olmagan — matn
    tushunarsiz, mijoz/model yo'q. Yo'qotadigan narsa yo'q. Ishga olingan
    zayavkada esa bu amal ISHLAMAYDI (9-to'plam §1): yarim yo'ldagi
    noaniqlik uchun `ask-sales` (konfiguratsiya joyida qoladi), ishni
    tashlash uchun `release` bor. `returned` — sales'ning stoli, hovuzdan
    chiqadi (boshqa engineer olib qo'yib, izoh o'qilmay qolmasin).
    """
    from rest_framework.exceptions import PermissionDenied, ValidationError

    from apps.configurator.models import ConfigurationRequest, ConfigurationRequestEvent
    from apps.core.models import Notification

    if not (user.is_admin or user.is_engineer):
        raise PermissionDenied('Zayavkani engineer (yoki admin) qaytaradi.')
    if request_obj.status != ConfigurationRequest.Status.NEW:
        raise ValidationError({
            'detail': (
                'Ishga olingan zayavka qaytarilmaydi — aniqlashtirish uchun '
                'konfiguratsiyadan so\'rang (ask-sales) yoki ishni hovuzga '
                'qaytaring (release).'
            ),
        })
    if not (comment or '').strip():
        raise ValidationError({
            'comment': 'Izoh majburiy — sales nimani tuzatishni bilishi kerak.',
        })

    request_obj.status = ConfigurationRequest.Status.RETURNED
    request_obj.save()
    log_request_event(
        request_obj, ConfigurationRequestEvent.Stage.RETURNED, user, comment,
    )

    if request_obj.created_by:
        Notification.objects.create(
            user=request_obj.created_by,
            title=f'{request_obj.number}: zayavka qaytarildi',
            message=comment,
            level=Notification.Level.WARNING,
            entity='ConfigurationRequest',
            object_id=str(request_obj.pk),
        )
    return request_obj


def release_request(request_obj, user, comment):
    """Engineer ishni hovuzga qaytaradi (9-to'plam §2, C holati).

    Zayavkada kamchilik yo'q — muammo engineerda (vaqti yo'q). Zayavka
    `new` ga qaytadi (RETURNED emas: sales'da tuzatadigan narsa yo'q),
    hovuzdagi boshqa engineer oladi. Ochilgan konfiguratsiya bekor bo'lib
    broni bo'shaydi: egasiz yarim tarkib keyingi engineerni chalg'itardi,
    mol behuda qulflanib turardi — keyingi `take` toza chernovik ochadi.
    SLA soati noldan boshlanadi — yangi engineer oldingisining kechikishi
    uchun qizil bo'lmaydi (tarix `RELEASED` yozuvida qoladi).
    """
    from rest_framework.exceptions import PermissionDenied, ValidationError

    from apps.configurator.models import (
        Configuration,
        ConfigurationRequest,
        ConfigurationRequestEvent,
    )
    from apps.core.models import Notification

    if not user.is_admin:
        if not (user.is_engineer and request_obj.taken_by_id == user.id):
            raise PermissionDenied(
                'Ishni faqat uni olgan engineer (yoki admin) qaytaradi.',
            )
    if request_obj.status != ConfigurationRequest.Status.IN_PROGRESS:
        raise ValidationError({
            'detail': 'Faqat ishga olingan zayavka hovuzga qaytariladi.',
        })
    if not (comment or '').strip():
        raise ValidationError({
            'comment': 'Izoh majburiy — zanjir nega to\'xtaganining yagona izi.',
        })

    configuration = request_obj.configuration
    if configuration and configuration.status not in {
        Configuration.Status.CANCELLED, Configuration.Status.SOLD,
    }:
        configuration.status = Configuration.Status.CANCELLED
        configuration.cancel_reason = comment  # 8-to'plam §4
        configuration.save()
        from apps.inventory.services import release_reservations

        release_reservations(
            configuration=configuration, user=user,
            note=f'{request_obj.number} hovuzga qaytarildi: {comment}',
        )

    request_obj.status = ConfigurationRequest.Status.NEW
    request_obj.taken_by = None
    request_obj.configuration = None
    request_obj.save()
    log_request_event(
        request_obj, ConfigurationRequestEvent.Stage.RELEASED, user, comment,
    )

    # Hovuz xabar oladi (amalni bajarganning o'ziga emas), sales esa INFO —
    # uning zanjiri kechikadi va buni bilishi kerak
    notify_engineers_about_request(request_obj, exclude=user)
    if request_obj.created_by:
        Notification.objects.create(
            user=request_obj.created_by,
            title=f'{request_obj.number}: engineer ishni hovuzga qaytardi',
            message=f'{comment} — zayavkani boshqa engineer oladi.',
            level=Notification.Level.INFO,
            entity='ConfigurationRequest',
            object_id=str(request_obj.pk),
        )
    return request_obj


def resend_request(request_obj, user):
    """Sales tuzatib qayta yuboradi (B15): `returned` → `new`, hovuzga qaytadi."""
    from rest_framework.exceptions import PermissionDenied, ValidationError

    from apps.configurator.models import ConfigurationRequest, ConfigurationRequestEvent

    if not user.is_admin:
        if not user.is_sales:
            raise PermissionDenied('Qayta yuborishni sales (egasi) bajaradi.')
        if request_obj.created_by_id and request_obj.created_by_id != user.id:
            raise PermissionDenied('Bu zayavka sizniki emas.')
    if request_obj.status != ConfigurationRequest.Status.RETURNED:
        raise ValidationError({
            'detail': 'Faqat qaytarilgan zayavka qayta yuboriladi.',
        })

    request_obj.status = ConfigurationRequest.Status.NEW
    request_obj.save()
    log_request_event(request_obj, ConfigurationRequestEvent.Stage.RESENT, user)
    notify_engineers_about_request(request_obj)
    return request_obj


def cancel_chain(document, user, reason):
    """Zanjirni butunlay to'xtatadi (B12/B17, §3.9): SHT, CFG, ZVK, bronlar.

    Uch kirish nuqtasi (shartnoma, konfiguratsiya, zayavka) — natija bitta.
    Boshlang'ich to'lov kelgan shartnoma BEKOR QILINMAYDI: pul qaytarish
    alohida rasmiylashtiriladigan ish. To'langan/buyurtma qilingan TLD ham
    tegilmaydi — mol baribir keladi, faqat ogohlantirish qaytadi.
    """
    from django.db.transaction import atomic
    from django.utils.timezone import now
    from rest_framework.exceptions import PermissionDenied, ValidationError

    from apps.configurator.models import (
        Configuration,
        ConfigurationRequest,
        ConfigurationRequestEvent,
    )
    from apps.core.models import Notification
    from apps.core.services import resolve_notifications
    from apps.inventory.services import release_reservations
    from apps.procurement.models import Replenishment, ReplenishmentEvent
    from apps.sales.models import Contract, ContractApproval

    if not (reason or '').strip():
        raise ValidationError({
            'reason': 'Sabab majburiy — zanjir nima uchun to\'xtagani tarixda qolsin.',
        })

    # Kirish nuqtasidan zanjirni yig'amiz
    configuration = contract = request_obj = None
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
    if configuration is not None and contract is None:
        contract = (
            configuration.contracts
            .exclude(status=Contract.Status.CANCELLED)
            .order_by('-id')
            .first()
        )

    # Kim: zanjir egasi (sales) yoki admin
    if not user.is_admin:
        owner_ids = {
            request_obj.created_by_id if request_obj else None,
            contract.created_by_id if contract else None,
        }
        if not (user.is_sales and user.id in owner_ids):
            raise PermissionDenied(
                'Zanjirni egasi (sales) yoki admin bekor qiladi.',
            )

    # §3.9: pul qabul qilingan zanjir bekor qilinmaydi
    if contract is not None and contract.payments.exists():
        raise ValidationError({
            'detail': (
                "Pul qabul qilingan — bekor qilib bo'lmaydi; qaytarish alohida "
                'rasmiylashtiriladi.'
            ),
        })

    warnings = []
    cancelled = {'contract': None, 'configuration': None, 'request': None}
    with atomic():
        if contract is not None and contract.status != Contract.Status.CANCELLED:
            step = (
                ContractApproval.Step.ADMIN
                if contract.status == Contract.Status.PENDING_ADMIN
                else ContractApproval.Step.BUGALTER
            )
            contract.status = Contract.Status.CANCELLED
            contract.save()
            ContractApproval.objects.create(
                contract=contract, step=step,
                decision=ContractApproval.Decision.REJECTED,
                comment=f'Zanjir bekor qilindi: {reason}',
                decided_by=user,
            )
            release_reservations(contract=contract, user=user, note=reason)
            cancelled['contract'] = contract.number

        if configuration is not None and configuration.status != Configuration.Status.CANCELLED:
            configuration.status = Configuration.Status.CANCELLED
            # 8-to'plam §4: "nega to'xtadi?" — hujjatning o'zida
            configuration.cancel_reason = reason
            configuration.save()
            release_reservations(configuration=configuration, user=user, note=reason)
            cancelled['configuration'] = configuration.number

        if request_obj is not None and request_obj.status != ConfigurationRequest.Status.CANCELLED:
            request_obj.status = ConfigurationRequest.Status.CANCELLED
            request_obj.save()
            log_request_event(
                request_obj, ConfigurationRequestEvent.Stage.CANCELLED, user, reason,
            )
            cancelled['request'] = request_obj.number

        # Ochiq TLD: hali to'lanmagani bekor bo'ladi; to'langani tegilmaydi
        if configuration is not None:
            for replenishment in configuration.replenishments.all():
                if replenishment.status in {
                    Replenishment.Status.DRAFT,
                    Replenishment.Status.PENDING_SALES,
                    Replenishment.Status.PENDING_BUGALTER,
                    Replenishment.Status.PENDING_ADMIN,
                    Replenishment.Status.REJECTED,
                }:
                    replenishment.status = Replenishment.Status.CANCELLED
                    replenishment.save()
                    ReplenishmentEvent.objects.create(
                        replenishment=replenishment,
                        stage=ReplenishmentEvent.Stage.NOTE,
                        comment=f'Zanjir bekor qilindi: {reason}',
                        happened_at=now(),
                        created_by=user,
                    )
                elif replenishment.is_open:
                    warnings.append(
                        f'{replenishment.number} ochiq qoladi — mol baribir keladi.',
                    )

        # 4-to'plam §4: zanjirning barcha ochiq eslatmalari yopiladi
        for entity, obj in (
            ('Contract', contract),
            ('Configuration', configuration),
            ('ConfigurationRequest', request_obj),
        ):
            if obj is not None:
                resolve_notifications(entity, obj.pk)

        # Qatnashchilarga bitta xabar
        recipients = {
            request_obj.created_by if request_obj else None,
            configuration.created_by if configuration else None,
            contract.created_by if contract else None,
        }
        number = (
            (request_obj and request_obj.number)
            or (configuration and configuration.number)
            or (contract and contract.number)
        )
        for recipient in recipients:
            if recipient is None or recipient.pk == user.pk:
                continue
            Notification.objects.create(
                user=recipient,
                title=f'{number}: zanjir bekor qilindi',
                message=f'{user.display_name}: {reason}',
                level=Notification.Level.WARNING,
                entity='ConfigurationRequest' if request_obj else 'Contract',
                object_id=str((request_obj or contract or configuration).pk),
            )

    return {'cancelled': cancelled, 'warnings': warnings, 'reason': reason}


def notify_engineers_about_request(request_obj, exclude=None):
    """Yangi zayavka haqida barcha faol engineerlarga eslatma (3-xato tuzatmasi).

    `exclude` — 9-to'plam §2: ishni hovuzga qaytargan engineerning o'ziga
    xabar yuborilmaydi.
    """
    from apps.accounts.models import User
    from apps.core.models import Notification

    engineers = User.objects.filter(role=User.Role.ENGINEER, is_active=True)
    if exclude is not None:
        engineers = engineers.exclude(pk=exclude.pk)
    for engineer in engineers:
        Notification.objects.create(
            user=engineer,
            title=f'{request_obj.number}: yangi zayavka',
            message=(request_obj.text or '')[:500],
            level=Notification.Level.INFO,
            entity='ConfigurationRequest',
            object_id=str(request_obj.pk),
        )
