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


def _owning_request(configuration, **filters):
    """Konfiguratsiya ortidagi zayavka — 12-§2 (B): qo'shimcha model qatori
    bo'lsa, `ConfigurationRequest.configuration` bo'sh qoladi (faqat
    `ConfigurationRequestLine.configuration` to'ladi), shuning uchun
    asosiy FK topolmasa qator orqali ham qidiriladi.
    """
    request_obj = (
        configuration.requests.filter(**filters).order_by('-created_at').first()
    )
    if request_obj is not None:
        return request_obj
    line = (
        configuration.extra_request_lines
        .filter(**{f'request__{k}': v for k, v in filters.items()})
        .select_related('request')
        .order_by('-id')
        .first()
    )
    return line.request if line else None


def deal_has_multiple_models(request_obj):
    """14-§1: "bitta shart" — hamma yangi mantiq shunga bog'liq.

    Savdoda qo'shimcha MODEL turidagi qator (`kind=model`) bo'lmasa,
    zayavkada bitta model bor — yangi ko'p-modelli mantiq butunlay
    o'chiq qoladi va oqim bugungidek ishlaydi. Har bo'limda shu funksiya
    orqali tekshiriladi — qoida bitta joyda turadi.
    """
    from apps.configurator.models import ConfigurationRequestLine

    if request_obj is None:
        return False
    return request_obj.lines.filter(kind=ConfigurationRequestLine.Kind.MODEL).exists()


def _deal_models_for_request(request_obj):
    """14-§6/§7/§8: savdodagi barcha model konfiguratsiyalari — asosiy birinchi.

    Bo'sh ro'yxat — zayavka yo'q. Bitta modelli savdoda ham ishlaydi
    (natija bitta elementli ro'yxat) — chaqiruvchilar o'zlari
    `deal_has_multiple_models` bilan tekshiradi.
    """
    from apps.configurator.models import ConfigurationRequestLine

    if request_obj is None:
        return []
    models = []
    if request_obj.configuration_id:
        models.append(request_obj.configuration)
    models += [
        line.configuration
        for line in request_obj.lines.filter(
            kind=ConfigurationRequestLine.Kind.MODEL, configuration__isnull=False,
        ).select_related('configuration').order_by('id')
    ]
    return models


def _deal_model_row(configuration, is_primary):
    return {
        'id': configuration.id,
        'number': configuration.number,
        'base_product_name': configuration.base_product.name,
        'quantity': configuration.quantity,
        'mode': configuration.mode,
        'status': configuration.status,
        'status_display': configuration.get_status_display(),
        'missing_count': (
            0 if configuration.status == configuration.Status.CANCELLED
            else len(configuration.missing_items)
        ),
        'assembled_at': configuration.assembled_at,
        'is_primary': is_primary,
    }


def _deal_sibling_contract(configuration):
    """14-§3(3b): savdodagi BOSHQA model orqali ochilgan shartnoma bormi?

    Holatidan qat'i nazar qaytariladi — `approve_configuration`dagi mavjud
    tekshiruv (`status != DRAFT`) uni ko'rib, "qoralama allaqachon ketib
    qolgan" chegaraviy holatda tushunarli 400 beradi (§3, "Chegaraviy
    holat"). Faqat DRAFT bo'lsa jimgina filtrlansa, bu holat hech qachon
    yuzaga kelmasdi — o'rniga sukut bo'yicha yangi shartnoma ochilib ketardi.
    """
    request_obj = _owning_request(configuration)
    if not deal_has_multiple_models(request_obj):
        return None

    for sibling in _deal_models_for_request(request_obj):
        if sibling.id == configuration.id:
            continue
        sibling_contract = sibling.active_contract
        if sibling_contract is not None:
            return sibling_contract
    return None


def build_deal(request_obj):
    """14-§2: savdo bloki — bitta `ConfigurationRequest` atrofidagi hamma
    hujjat (N model, M tovar, bitta shartnoma/TLD/ACT). Ko'p modelli
    savdoda `null` emas — bitta modelli bo'lsa ham to'liq shakl qaytadi,
    front bitta qoida bilan ishlaydi: `deal.models.length > 1`.

    Bitta modelli zayavkada (`deal_has_multiple_models` yolg'on) — `None`,
    front eski (bugungi) ko'rinishni chizadi.
    """
    from apps.configurator.models import ConfigurationRequestLine

    if not deal_has_multiple_models(request_obj):
        return None

    primary = request_obj.configuration
    models = [
        _deal_model_row(cfg, is_primary=(primary is not None and cfg.id == primary.id))
        for cfg in _deal_models_for_request(request_obj)
    ]

    items = [
        {
            'id': line.id,
            'product': line.base_product_id,
            'product_name': line.base_product.name,
            'quantity': line.quantity,
            'contract_item': line.contract_item_id,
        }
        for line in (
            request_obj.lines.filter(kind=ConfigurationRequestLine.Kind.ITEM)
            .select_related('base_product')
            .order_by('id')
        )
    ]

    # Savdoning umumiy hujjatlari — istalgan model orqali topiladi, hammasi
    # (§3 dan keyin) bitta shartnomaga, (§6 dan keyin) bitta TLDga yig'iladi
    deal_models = _deal_models_for_request(request_obj)
    contract = None
    act = None
    for configuration in deal_models:
        if contract is None:
            contract = configuration.active_contract
        if act is None and configuration.act_id:
            act = configuration.act
    replenishment = (
        chain_open_replenishment(configuration=primary) if primary else None
    ) or next(
        (cfg.last_replenishment for cfg in deal_models if cfg.last_replenishment), None,
    )

    return {
        'request': request_obj.id,
        'request_number': request_obj.number,
        'models': models,
        'items': items,
        'contract': (
            {'id': contract.id, 'number': contract.number, 'status': contract.status}
            if contract else None
        ),
        'replenishment': (
            {
                'id': replenishment.id, 'number': replenishment.number,
                'status': replenishment.status, 'is_open': replenishment.is_open,
            }
            if replenishment else None
        ),
        'act': (
            {'id': act.id, 'number': act.number} if act else None
        ),
    }


_TLD_ADDABLE_STATUSES = ('draft', 'pending_sales', 'pending_bugalter', 'rejected')


def detach_configuration(configuration, user, reason, target='cancel'):
    """14-§5: modelni savdodan chiqarish — mijoz voz kechdi yoki moli oylab
    kelmayapti, birinchisi esa tayyor. `cancel_chain` butun zanjirni (SHT
    ham, tayyor model ham) o'ldiradi — bu esa bitta qatorni olib tashlaydi.

    `target='cancel'` — konfiguratsiya `cancelled`, bronlari bo'shaydi.
    `target='separate'` — konfiguratsiya savdodan chiqadi va O'ZIGA yangi
    `draft` shartnoma oladi. Ikkala holatda ham shartnomadagi qator
    o'chadi va summa qayta hisoblanadi.

    Ruxsat: shartnoma (yoki savdo — hali shartnomasiz bo'lsa) egasi sales,
    yoki admin. Bloklanadi: shartnoma `draft` emas bo'lsa — pul kelgan
    shartnomadan model olib tashlanmaydi (qaytarish/bekor qilish oqimi bor).

    16-§B5: (a) chiqarilayotgan model uchun ochilgan TLD qatorlari —
    hisob hali tasdiq yo'liga chiqmagan bo'lsa o'chiriladi, aks holda
    (mol baribir keladi) qoladi va `warnings`da aytiladi; (b) allaqachon
    yig'ilgan model uchun ombor harakatlari qaytarilmaydi — variant
    omborda qoladi, `warnings`da aytiladi; (c) chiqarilayotgan ASOSIY
    model bo'lsa, savdodagi eng eski tirik model asosiy bo'lib ko'tariladi
    (tirik model umuman qolmasa — 400, `cancel` orqali butun savdo yopiladi).
    """
    from django.db.transaction import atomic
    from rest_framework.exceptions import PermissionDenied, ValidationError

    from apps.configurator.models import Configuration, ConfigurationRequestEvent
    from apps.sales.models import Contract

    if not (reason or '').strip():
        raise ValidationError({'reason': "Sabab majburiy — savdo tarixida qolsin."})
    if target not in ('cancel', 'separate'):
        raise ValidationError({'target': "Ruxsat etilgan qiymatlar: cancel, separate."})

    contract = configuration.active_contract
    request_obj = _owning_request(configuration)
    owner_id = (
        (contract.created_by_id if contract else None)
        or (request_obj.created_by_id if request_obj else None)
    )
    if not user.is_admin and not (user.is_sales and owner_id == user.id):
        raise PermissionDenied('Bu amalni shartnoma egasi (sales) yoki admin bajaradi.')

    if contract is not None and contract.status != Contract.Status.DRAFT:
        raise ValidationError({
            'detail': (
                f'{contract.number} qoralama emas — pul kelgan shartnomadan '
                "model olib tashlanmaydi. Qaytarish yoki bekor qilish "
                'oqimidan foydalaning.'
            ),
            'contract': contract.pk,
            'contract_status': contract.status,
        })

    is_primary = bool(request_obj and request_obj.configuration_id == configuration.id)
    is_deal = deal_has_multiple_models(request_obj)
    promoted = None
    if is_primary and is_deal:
        remaining = [
            cfg for cfg in _deal_models_for_request(request_obj)
            if cfg.id != configuration.id and cfg.status != Configuration.Status.CANCELLED
        ]
        if not remaining:
            raise ValidationError({
                'detail': (
                    f"{configuration.number} — savdodagi yagona tirik model. "
                    "Uni detach bilan emas, butun savdoni `cancel` bilan yoping."
                ),
            })
        promoted = min(remaining, key=lambda cfg: cfg.id)

    warnings = []
    with atomic():
        if contract is not None:
            removed = contract.items.filter(configuration=configuration).first()
            if removed is not None:
                removed.delete()
            contract.total_amount = contract.items_total_with_vat
            contract.save(update_fields=['total_amount'])
            from apps.inventory.services import sync_contract_reservations

            sync_contract_reservations(contract)

        # 16-§B5(a): TLD qatorlari — hisob hali tasdiq yo'liga chiqmagan
        # bo'lsa o'chiriladi, aks holda mol baribir keladi va omborga tushadi
        for item in configuration.replenishment_items.select_related('replenishment'):
            rep = item.replenishment
            if rep.status in _TLD_ADDABLE_STATUSES:
                item.delete()
            else:
                warnings.append(
                    f'{rep.number}: {configuration.number} uchun buyurtma '
                    "qilingan mol baribir keladi va omborga kirim bo'ladi.",
                )

        # 16-§B5(b): yig'ilgan bo'lsa ombor harakatlari qaytarilmaydi
        if configuration.assembled_at and configuration.variant_id:
            warnings.append(
                f"{configuration.number} allaqachon yig'ilgan — "
                f'{configuration.variant.sku} omborda qoladi.',
            )

        new_contract = None
        if target == 'cancel':
            configuration.status = Configuration.Status.CANCELLED
            configuration.cancel_reason = reason
            configuration.save()
            from apps.inventory.services import release_reservations

            release_reservations(configuration=configuration, user=user, note=reason)
        else:
            client = _configuration_client(configuration)
            from apps.sales.services import create_contract_from_configuration

            new_contract = create_contract_from_configuration(configuration, user, client)

        # 16-§B5(c): asosiy model chiqmoqda — eng eski tirik model ko'tariladi
        if promoted is not None:
            request_obj.configuration = promoted
            request_obj.save(update_fields=['configuration'])
            promoted_line = request_obj.lines.filter(configuration=promoted).first()
            if promoted_line is not None:
                promoted_line.delete()

        log_request_event(
            request_obj, ConfigurationRequestEvent.Stage.NOTE, user,
            f"{configuration.number}: savdodan chiqarildi "
            f"({'bekor qilindi' if target == 'cancel' else 'alohida shartnoma oldi'}) — {reason}"
            + (f' Yangi asosiy model: {promoted.number}.' if promoted is not None else ''),
        )

    return {
        'configuration': configuration.number,
        'target': target,
        'reason': reason,
        'contract': (
            {'id': new_contract.id, 'number': new_contract.number}
            if new_contract else None
        ),
        'promoted_primary': promoted.number if promoted is not None else None,
        'warnings': warnings,
    }


def _deal_contract_for_request(request_obj):
    """16-§B3: savdodagi (istalgan model orqali) ochilgan shartnoma bormi?

    `_deal_sibling_contract` dan farqi — bu yerda "o'zini" chiqarib
    tashlaydigan konfiguratsiya yo'q (yangi qator hali mavjud emas).
    """
    for cfg in _deal_models_for_request(request_obj):
        if cfg.active_contract is not None:
            return cfg.active_contract
    return None


def add_request_line(request_obj, user, *, kind, base_product, quantity, text='', mode=None):
    """16-§B2: savdo boshlangandan keyin YANGI model/tovar qo'shish.

    Bugungacha bunga umuman yo'l yo'q edi — `lines[]` faqat zayavka
    YARATILGANDA o'qilardi. Mijoz fikridan qaytsa ("bu emas, manabu
    kerak") yoki qo'shimcha narsa so'rasa, endi shu orqali qo'shiladi —
    "almashtirish" alohida amal emas, shu + `detach` (16-§B4).

    Kim: zayavka egasi sales yoki admin — bu mijozning xohishi, texnik
    qaror emas (engineer emas, B2).

    Zayavka allaqachon ishga olingan bo'lsa (`in_progress` va undan
    keyin) — MODEL turidagi qatorga darhol chernovik ochiladi, xuddi
    `take_request` dagi kabi. Hali `new` bo'lsa — ochilmaydi, engineer
    ishga olganda hammasi birga ochiladi (bugungi xulq, B2).
    """
    from django.db.transaction import atomic
    from rest_framework.exceptions import PermissionDenied, ValidationError

    from apps.configurator.models import Configuration, ConfigurationRequest, ConfigurationRequestLine
    from apps.core.models import Notification
    from apps.inventory.models import Product
    from apps.sales.models import Contract

    if not (user.is_admin or user.is_sales):
        raise PermissionDenied("Savdoga model/tovar qo'shishni sales (yoki admin) bajaradi.")
    if not user.is_admin and request_obj.created_by_id != user.id:
        raise PermissionDenied('Bu savdo sizniki emas.')
    if kind not in ConfigurationRequestLine.Kind.values:
        raise ValidationError({
            'kind': f"Ruxsat etilgan qiymatlar: {', '.join(ConfigurationRequestLine.Kind.values)}.",
        })
    if base_product is None:
        raise ValidationError({'base_product': 'Mahsulot tanlanishi shart.'})
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        raise ValidationError({'quantity': "Miqdor butun son bo'lishi kerak."})
    if quantity < 1:
        raise ValidationError({'quantity': 'Miqdor kamida 1 dona bo\'ladi.'})
    if kind == ConfigurationRequestLine.Kind.MODEL and base_product.kind != Product.Kind.MACHINE:
        raise ValidationError({
            'base_product': (
                "model turidagi qator faqat tayyor model bo'lishi mumkin — "
                'tovar bo\'lsa `item` turini tanlang.'
            ),
        })
    if mode and mode not in Configuration.Mode.values:
        raise ValidationError({'mode': f"Noto'g'ri rejim: {mode}."})
    if request_obj.status in (
        ConfigurationRequest.Status.CANCELLED, ConfigurationRequest.Status.ARCHIVED,
    ):
        raise ValidationError({
            'detail': f"{request_obj.number} yopilgan — savdoga yangi narsa qo'shilmaydi.",
        })

    configuration = None
    regressed = False
    with atomic():
        request_obj = ConfigurationRequest.objects.select_for_update().get(pk=request_obj.pk)

        # B3: shartnoma allaqachon bugalterga (yoki undan nariga) ketgan
        # bo'lsa — hujjat qulflangan, yangi model qo'shib bo'lmaydi
        contract = _deal_contract_for_request(request_obj)
        if contract is not None and contract.status != Contract.Status.DRAFT:
            raise ValidationError({
                'detail': (
                    f'{request_obj.number} {contract.get_status_display().lower()} '
                    "— savdoga yangi model qo'shib bo'lmaydi. Bugalter "
                    "shartnomani qaytarsin, keyin qo'shing."
                ),
                'contract': contract.pk,
                'contract_status': contract.status,
            })

        line = ConfigurationRequestLine.objects.create(
            request=request_obj, kind=kind, base_product=base_product,
            quantity=quantity, text=text,
        )

        if (
            kind == ConfigurationRequestLine.Kind.MODEL
            and request_obj.status != ConfigurationRequest.Status.NEW
        ):
            from apps.inventory.services import main_warehouse, sync_configuration_reservations

            configuration = Configuration.objects.create(
                base_product=base_product,
                client=request_obj.client,
                warehouse=request_obj.warehouse or main_warehouse(),
                mode=mode or Configuration.Mode.BUILD,
                quantity=quantity,
                note=f'{request_obj.number}: {text or base_product.name}',
                created_by=request_obj.taken_by,
            )
            copy_factory_spec(configuration)
            sync_configuration_reservations(configuration)
            line.configuration = configuration
            line.save(update_fields=['configuration'])

            # B5(e): savdo allaqachon ko'rikdan o'tayotgan bo'lsa (biror
            # sibling DRAFTdan nariga o'tgan) — yangi model uni orqaga
            # qaytaradi (`_deal_step` o'zi hisoblaydi), sales bundan xabardor bo'lsin
            regressed = any(
                cfg.status != Configuration.Status.DRAFT
                for cfg in _deal_models_for_request(request_obj)
                if cfg.id != configuration.id
            )

    if configuration is not None and request_obj.taken_by_id:
        Notification.objects.create(
            user=request_obj.taken_by,
            title=f"{request_obj.number}: yangi model qo'shildi",
            message=f"{configuration.number} ({base_product.name}) ishingizga qo'shildi.",
            level=Notification.Level.INFO,
            entity='Configuration',
            object_id=str(configuration.pk),
        )
    if regressed and request_obj.created_by_id:
        Notification.objects.create(
            user=request_obj.created_by,
            title=f'{request_obj.number}: savdo o\'zgardi',
            message="Yangi model qo'shildi — ko'rikdagi savdo qayta tekshiriladi.",
            level=Notification.Level.WARNING,
            entity='ConfigurationRequest',
            object_id=str(request_obj.pk),
        )
    return line, configuration


def delete_request_line(line, user):
    """16-§B5(f): tovar (`kind=item`) qatorini savdodan olib tashlash.

    Model qatorlari konfiguratsiyasi bor — ular `detach` orqali chiqadi
    (14-§5); bu funksiya faqat konfiguratorsiz TOVAR qatorlari uchun.
    Qatorning o'zini o'chirish chaqiruvchida (view `perform_destroy`,
    audit logi bilan birga) — bu funksiya faqat shartnoma tomonidagi
    yon ta'sirni (bog'liq `ContractItem`) tozalaydi va qulf tekshiradi.
    """
    from django.db.transaction import atomic
    from rest_framework.exceptions import PermissionDenied, ValidationError

    from apps.configurator.models import ConfigurationRequestLine
    from apps.sales.models import Contract

    if line.kind != ConfigurationRequestLine.Kind.ITEM:
        raise ValidationError({
            'detail': "Model turidagi qator faqat `detach` orqali chiqariladi.",
        })
    request_obj = line.request
    if not user.is_admin and not (user.is_sales and request_obj.created_by_id == user.id):
        raise PermissionDenied('Bu savdo sizniki emas.')

    with atomic():
        contract_item = line.contract_item
        if contract_item is not None:
            contract = contract_item.contract
            if contract.status != Contract.Status.DRAFT:
                raise ValidationError({
                    'detail': (
                        f'{contract.number} qoralama emas — pul kelgan '
                        "shartnomadan qator olib tashlanmaydi."
                    ),
                    'contract': contract.pk,
                    'contract_status': contract.status,
                })
            contract_item.delete()
            contract.total_amount = contract.items_total_with_vat
            contract.save(update_fields=['total_amount'])


def _configuration_owner_sales(configuration):
    """Konfiguratsiya ortidagi zayavka egasi (sales) — tasdiq va xabarlar unga."""
    request_obj = _owning_request(configuration, created_by__isnull=False)
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
        _owning_request(configuration),
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
            _owning_request(configuration),
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
    request_obj = _owning_request(configuration, client__isnull=False)
    return request_obj.client if request_obj else None


def approve_configuration(configuration, user, comment='', contract=None, separate_contract=False):
    """Sales texnik yechimni tasdiqlaydi — SHU YERDA shartnoma ochiladi (B1).

    YANGI OQIM: zanjir `CFG → SHT → pul → mol`. Tasdiq bilan draft shartnoma
    avtomatik ochiladi (egasi — zayavka sales'i), sales uni bugalterga
    yuboradi; ta'minot va yig'ish esa boshlang'ich to'lovdan keyin boshlanadi.

    12-§2 (C2): `contract` berilsa — bitta savdoda bir nechta model
    (mijoz bir suhbatda ikki xil narsa so'raganda). Yangi shartnoma
    ochilmaydi, aksincha shu MAVJUD qoralamaga yangi qator qo'shiladi.

    14-§3: shartnoma birlashtirish endi ODAT emas, QOIDA — `contract`
    berilmagan va `separate_contract` yolg'on bo'lsa, savdodagi BOSHQA
    model orqali ochilgan DRAFT shartnoma avtomatik topiladi va shu
    modelga ham o'sha qo'shiladi. `separate_contract=True` — mijoz buni
    ataylab alohida shartnoma qilishni so'ragan kamdan-kam holat uchun.
    """
    from apps.configurator.models import Configuration, ConfigurationApproval
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
    # 14-§3 (3b): faqat konfiguratsiyaning O'Z shartnomasi yo'q va sales
    # alohida so'ramagan bo'lsa — savdodagi boshqa modelning qoralamasi qidiriladi
    if contract is None and not separate_contract and configuration.active_contract is None:
        contract = _deal_sibling_contract(configuration)

    if contract is not None:
        from apps.sales.models import Contract

        if contract.status != Contract.Status.DRAFT:
            raise ValidationError({
                'detail': (
                    f'{contract.number} qoralama emas — bugalterga ketgan '
                    f'shartnomaga {configuration.number} ni unga qo\'shib '
                    'bo\'lmaydi. Bugalter shartnomani qaytarsin, yoki bu '
                    'modelni alohida shartnoma bilan davom ettiring '
                    '(`separate_contract: true`).'
                ),
                'contract': contract.pk,
                'contract_status': contract.status,
            })
        if contract.client_id != client.id:
            raise ValidationError({
                'detail': f'{contract.number} boshqa mijozniki — mijoz mos kelmadi.',
            })
        if not user.is_admin and contract.created_by_id and contract.created_by_id != user.id:
            raise ValidationError({'detail': f'{contract.number} sizniki emas.'})

    _decide_configuration(
        configuration, user, ConfigurationApproval.Decision.APPROVED, comment,
    )
    configuration.status = Configuration.Status.APPROVED
    configuration.save()
    # 4-to'plam §4: "ko'rib chiqing" vazifasi bajarildi — salesniki yopiladi
    from apps.core.services import resolve_notifications

    resolve_notifications('Configuration', configuration.pk, user=user)

    if contract is not None:
        _attach_configuration_to_contract(configuration, contract)
    elif configuration.active_contract is None:
        # B1: shartnoma zanjir boshida ochiladi (qaytadan tasdiqlashda mavjudi olinadi)
        from apps.sales.services import create_contract_from_configuration

        create_contract_from_configuration(configuration, user, client)

    resolved_contract = configuration.active_contract
    # 12-§2 (B3): zayavka holati ergashadi — lekin faqat BARCHA qatorlari
    # (qo'shimcha model va tovar qatorlari ham) tugagach; shu paytda hali
    # qo'shilmagan TOVAR qatorlari ham shartnomaga o'tadi
    _advance_request_after_configuration_approval(configuration, resolved_contract)
    if configuration.created_by:
        Notification.objects.create(
            user=configuration.created_by,
            title=f'{configuration.number}: texnik yechim tasdiqlandi',
            message=(
                f'Sales mijoz bilan kelishdi — {resolved_contract.number} '
                'shartnomasiga qo\'shildi. Ta\'minot va yig\'ish boshlang\'ich '
                'to\'lovdan keyin boshlanadi.'
                if resolved_contract else 'Sales mijoz bilan kelishdi.'
            ),
            level=Notification.Level.INFO,
            entity='Configuration',
            object_id=str(configuration.pk),
        )
    return configuration


def _advance_request_after_configuration_approval(configuration, contract):
    """12-§2 (B3): zayavka faqat BARCHA qatori tugagach DONE bo'ladi.

    "Qator" ikki xil: MODEL (bu funksiya chaqirilganda ANIQ shu
    konfiguratsiya orqali tugaydi) va TOVAR (konfiguratorsiz — shartnoma
    mavjud bo'lishi bilanoq, hali qo'shilmagan bo'lsa, shu yerda
    ContractItem sifatida qo'shiladi). Bitta qatorli (oddiy) zayavkada bu
    darhol DONE degani — eski xulq o'zgarmaydi.
    """
    from apps.configurator.models import ConfigurationRequest, ConfigurationRequestLine

    request_obj = ConfigurationRequest.objects.filter(configuration=configuration).first()
    if request_obj is None:
        line = configuration.extra_request_lines.select_related('request').first()
        request_obj = line.request if line else None
    if request_obj is None or request_obj.status != ConfigurationRequest.Status.IN_PROGRESS:
        return

    if contract is not None:
        from apps.sales.models import ContractItem

        pending_items = list(request_obj.lines.filter(
            kind=ConfigurationRequestLine.Kind.ITEM, contract_item__isnull=True,
        ))
        for line in pending_items:
            item = ContractItem.objects.create(
                contract=contract, product=line.base_product, quantity=line.quantity,
                unit_price=line.base_product.stock_price,
            )
            line.contract_item = item
            line.save(update_fields=['contract_item'])
        if pending_items:
            contract.total_amount = contract.items_total_with_vat
            contract.save(update_fields=['total_amount'])

    if request_obj.is_fully_done:
        request_obj.status = ConfigurationRequest.Status.DONE
        request_obj.save(update_fields=['status'])


def _attach_configuration_to_contract(configuration, contract):
    """12-§2 (C2): mavjud qoralama shartnomaga yangi model qatori qo'shiladi.

    `create_contract_from_configuration` bilan bir xil qator mantig'i —
    tayyor variant (odatda hali yo'q) narxi konfiguratsiyadan, QQS default.
    """
    from apps.sales.models import ContractItem

    ContractItem.objects.create(
        contract=contract,
        product=configuration.variant or configuration.base_product,
        quantity=configuration.quantity,
        unit_price=configuration.total_price,
        configuration=configuration,
    )
    contract.total_amount = contract.items_total_with_vat
    contract.save()
    from apps.inventory.services import sync_contract_reservations

    sync_contract_reservations(contract)


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
    # draft/rejected) — qatordagi son va jami ham ergashadi. 12-§2 C: qator
    # `configuration` FK orqali topiladi — ikkinchi model bo'lsa ham to'g'ri
    from apps.sales.models import Contract, ContractItem

    contract_item = (
        ContractItem.objects
        .filter(configuration=configuration)
        .exclude(contract__status=Contract.Status.CANCELLED)
        .select_related('contract')
        .order_by('-id')
        .first()
    )
    contract = contract_item.contract if contract_item else None
    if contract and contract.status in {
        Contract.Status.DRAFT, Contract.Status.REJECTED,
    }:
        contract_item.quantity = quantity
        contract_item.save()
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


def deal_act_suggestion_text(request_obj):
    """14-§7 (2): ACT matni savdo darajasida — har YIG'ILGAN model uchun
    bitta abzats. Hali yig'ilmagan modellar matnga kirmaydi — ACT
    bajarilgan ishning hujjati.
    """
    models = _deal_models_for_request(request_obj)
    paragraphs = [act_suggestion_text(cfg) for cfg in models if cfg.assembled_at]
    return '\n\n'.join(paragraphs)


# ---------------------------------------------------------------------------
# 16-§A: amallar savdo (ConfigurationRequest) darajasida.
#
# A0: qaror savdoniki (bitta bosish — submit/approve/reject/request-prices/
# finalize), mehnat modelniki (yig'ish — atomar emas, model-model qaytadi).
# Model darajasidagi funksiyalar (submit_configuration va h.k.) O'ZGARMAYDI
# va o'chirilmaydi — bitta modelli zayavkada yagona yo'l, ko'p modelli
# savdoda ham qoladi (admin bitta modelni qo'lda surishi kerak bo'lganda).
# Bu funksiyalar ularning ustidan savdo bo'yicha yuradi.
# ---------------------------------------------------------------------------

def deal_submit(request_obj, user):
    """16-§A2: savdodagi barcha `draft` modellarni ko'rikka yuboradi.

    Hammasi yoki hech nima: biror model tayyor bo'lmasa (tarkib bo'sh,
    narxsiz qator, yoki allaqachon boshqa bosqichda/bekor qilingan) —
    HECH biri o'zgarmaydi, `blocked` ro'yxati sabab bilan qaytadi.
    Bekor qilingan modellar hisobga kirmaydi (o'lik, yo'lni to'smaydi).
    """
    from rest_framework.exceptions import PermissionDenied, ValidationError

    from apps.configurator.models import Configuration

    if not (user.is_admin or user.is_engineer):
        raise PermissionDenied('Texnik yechimni Engineer yuboradi.')

    active = [
        cfg for cfg in _deal_models_for_request(request_obj)
        if cfg.status != Configuration.Status.CANCELLED
    ]
    if not active:
        raise ValidationError({'detail': "Savdoda tirik model yo'q."})

    blocked = []
    for cfg in active:
        if cfg.status != Configuration.Status.DRAFT:
            blocked.append({
                'id': cfg.id, 'number': cfg.number, 'reason': 'wrong_status',
                'message': f"'{cfg.get_status_display()}' holatida — chernovik emas.",
            })
            continue
        if not cfg.items.exists():
            blocked.append({
                'id': cfg.id, 'number': cfg.number, 'reason': 'no_items',
                'message': "Tarkib bo'sh",
            })
            continue
        for item in cfg.items.filter(unit_price=0):
            item.save()
        if cfg.items_without_price:
            blocked.append({
                'id': cfg.id, 'number': cfg.number, 'reason': 'needs_price',
                'message': 'Narxsiz qator bor',
            })
    if blocked:
        raise ValidationError({
            'detail': f'{len(active)} ta modeldan {len(blocked)} tasi yuborishga tayyor emas.',
            'blocked': blocked,
        })

    return [submit_configuration(cfg, user) for cfg in active]


def deal_approve(request_obj, user, comment=''):
    """16-§A2: savdodagi barcha `pending_sales` modellarni tasdiqlaydi.

    Har biri o'zining `approve_configuration`sidan o'tadi — 14-§3 dagi
    avtomatik birlashtirish (ikkinchi modeldan boshlab mavjud qoralamaga
    qo'shiladi) shu bilan BITTA shartnomani o'zi kafolatlaydi.
    `separate_contract` bu yerda qabul qilinmaydi — savdo darajasidagi
    tasdiq ta'rifan bitta shartnoma degani.
    """
    from rest_framework.exceptions import ValidationError

    from apps.configurator.models import Configuration

    pending = [
        cfg for cfg in _deal_models_for_request(request_obj)
        if cfg.status == Configuration.Status.PENDING_SALES
    ]
    if not pending:
        raise ValidationError({'detail': "Sales ko'rigidagi model yo'q."})
    return [approve_configuration(cfg, user, comment) for cfg in pending]


def deal_reject(request_obj, user, comment=''):
    """16-§A2: bitta izoh bilan barcha `pending_sales` modellarni qaytaradi."""
    from rest_framework.exceptions import ValidationError

    from apps.configurator.models import Configuration

    if not (comment or '').strip():
        raise ValidationError({'comment': "Izoh majburiy — engineer nimani tuzatishni bilsin."})
    pending = [
        cfg for cfg in _deal_models_for_request(request_obj)
        if cfg.status == Configuration.Status.PENDING_SALES
    ]
    if not pending:
        raise ValidationError({'detail': "Sales ko'rigidagi model yo'q."})
    return [reject_configuration(cfg, user, comment) for cfg in pending]


def deal_request_prices(request_obj, user):
    """16-§A2: savdodagi BARCHA modellarning narxsiz qatorlarini yig'ib,
    buyurtmachiga bitta to'plam qilib yuboradi.

    Eslatma baribir mahsulot bo'yicha (10-§1) — ikki modelda bir xil
    butlovchi bo'lsa bitta eslatma chiqadi (o'zi shunday ishlaydi, bu
    funksiya faqat javobda qaysi model uchun so'ralganini birlashtiradi).
    """
    from rest_framework.exceptions import ValidationError

    from apps.configurator.models import Configuration

    eligible_statuses = {
        Configuration.Status.DRAFT, Configuration.Status.PENDING_CLARIFICATION,
        Configuration.Status.PENDING_SALES,
    }
    by_product = {}
    for cfg in _deal_models_for_request(request_obj):
        if cfg.status not in eligible_statuses:
            continue
        for item in cfg.items.filter(unit_price=0):
            item.save()
        no_price = cfg.items_without_price
        if not no_price:
            continue
        request_prices(cfg, user)
        for item in no_price:
            row = by_product.setdefault(
                item.component_id, {'product': item.component, 'configurations': []},
            )
            row['configurations'].append(cfg.number)
    if not by_product:
        raise ValidationError({'detail': "Barcha qatorlarda narx bor — so'rov shart emas."})
    return [
        {'product': row['product'].id, 'name': row['product'].name, 'configurations': row['configurations']}
        for row in by_product.values()
    ]


def deal_assemble(request_obj, user):
    """16-§A2: savdodagi barcha `approved` modellarni ketma-ket yig'adi.

    A0: bu MEHNAT — atomar emas. Bitta model yig'ilsa ham muvaffaqiyat;
    qolgani mol kelgach qayta bosiladi. 400 faqat HECH BIRI yig'ilmaganda
    (yoki to'lov hali kelmagan bo'lsa — hammasi bitta shartnomaga bog'liq
    bo'lgani uchun bu holat baribir barchasiga baravar taalluqli).
    """
    from rest_framework.exceptions import ValidationError

    from apps.configurator.models import Configuration

    candidates = [
        cfg for cfg in _deal_models_for_request(request_obj)
        if cfg.status == Configuration.Status.APPROVED
    ]
    if not candidates:
        raise ValidationError({'detail': "Yig'ish uchun tasdiqlangan model yo'q."})

    assembled, pending = [], []
    for cfg in candidates:
        ok, missing = assemble_configuration(cfg, user, strict=False)
        if ok:
            assembled.append(cfg.number)
        else:
            pending.append({'number': cfg.number, 'missing': missing})
    if not assembled:
        raise ValidationError({
            'detail': "Hech biri yig'ilmadi — butlovchilar yetmayapti.",
            'pending': pending,
        })
    return {'assembled': assembled, 'pending': pending}


def deal_finalize(request_obj, user, *, act=None, client=None):
    """16-§A2: savdodagi barcha YIG'ILGAN modellarni yakunlaydi, BITTA ACT
    biriktiradi. ACT tanada bir marta beriladi — har bir modelga xuddi
    shu obyekt beriladi (birinchisidan keyingilar sibling-fallback bilan
    emas, aniq shu bilan bog'lanadi). Yig'ilmagan model yakunlanmaydi —
    `pending`da qaytadi.
    """
    from rest_framework.exceptions import ValidationError

    from apps.configurator.models import Configuration

    models = _deal_models_for_request(request_obj)
    candidates = [
        cfg for cfg in models
        if cfg.status == Configuration.Status.APPROVED and cfg.assembled_at
    ]
    if not candidates:
        raise ValidationError({'detail': "Yig'ilgan model yo'q — avval yig'ing (assemble)."})

    finalized, contract = [], None
    for cfg in candidates:
        cfg_result, cfg_contract, _moved = finalize_configuration(cfg, user, act=act, client=client)
        finalized.append(cfg_result.number)
        contract = contract or cfg_contract

    pending = [
        cfg.number for cfg in models
        if cfg.status == Configuration.Status.APPROVED and not cfg.assembled_at
    ]
    return {'finalized': finalized, 'pending': pending, 'contract': contract}


def deal_ask_sales(request_obj, user, comment):
    """16-§A3: savdoning yozishmasi = ASOSIY modelning yozishmasi.

    Savol asosiy modelga yoziladi (bitta suhbat, qaysi model sahifasida
    tursangiz ham xuddi shu ko'rinadi — serializer §A3.3), lekin
    savdodagi BARCHA `draft` modellar `pending_clarification`ga o'tadi:
    javobsiz turganda ikkinchi model ustida ishlashning ma'nosi yo'q —
    `submit` baribir bloklanadi. Butun savdo to'xtashi xato emas, maqsad.
    """
    from rest_framework.exceptions import ValidationError

    from apps.configurator.models import Configuration

    primary = request_obj.configuration
    if primary is None:
        raise ValidationError({'detail': "Zayavkada asosiy model yo'q."})
    result = ask_sales(primary, user, comment)
    for cfg in _deal_models_for_request(request_obj):
        if cfg.id != primary.id and cfg.status == Configuration.Status.DRAFT:
            cfg.status = Configuration.Status.PENDING_CLARIFICATION
            cfg.save(update_fields=['status'])
    return result


def deal_answer(request_obj, user, comment):
    """16-§A3: sales javobi — teskarisi, barcha modellarni `draft`ga qaytaradi."""
    from rest_framework.exceptions import ValidationError

    from apps.configurator.models import Configuration

    primary = request_obj.configuration
    if primary is None:
        raise ValidationError({'detail': "Zayavkada asosiy model yo'q."})
    result = answer_clarification(primary, user, comment)
    for cfg in _deal_models_for_request(request_obj):
        if cfg.id != primary.id and cfg.status == Configuration.Status.PENDING_CLARIFICATION:
            cfg.status = Configuration.Status.DRAFT
            cfg.save(update_fields=['status'])
    return result


def chain_open_replenishment(configuration=None, contract=None):
    """Zanjirdagi ochiq TLD — qaysi eshikdan kirilganidan qat'i nazar (11-§1).

    Zanjirga ikki eshik bor (konfiguratsiya va shartnoma) va avval har biri
    faqat o'z tomonini tekshirardi: engineer CFG'dan hisob ochgan bo'lsa ham
    sales SHT'dan ikkinchisini ocha olardi — bir xil mol ikki marta buyurtma
    qilinib, ikki marta to'lanardi. Bu 8-§3 dagi "bitta CFG'ga bitta SHT"
    xatosining aynan o'zi, faqat boshqa hujjatda.

    14-§6 (4): ko'p modelli SAVDODA bitta TLD — savdodagi istalgan modelda
    ochiq hisob bo'lsa, boshqasidan yangisi ochilmaydi (avval, 12-§2 C4
    davrida, aksincha edi: modellar hali alohida shartnomalarga ketishi
    mumkin edi, endi savdo bitta bo'lgani uchun qoida ham teskarilandi).
    Hisob savdoning ASOSIY modeliga bog'langan bo'lishi mumkin
    (`Replenishment.configuration`) — shuning uchun sibling'lar ham
    o'zining bevosita FK'si, ham `ReplenishmentItem.configuration` orqali
    tekshiriladi.
    """
    from apps.procurement.models import Replenishment

    if contract is not None and configuration is None:
        configuration = contract.configuration
    candidates = []
    if configuration is not None:
        request_obj = _owning_request(configuration)
        deal_models = (
            _deal_models_for_request(request_obj)
            if deal_has_multiple_models(request_obj) else [configuration]
        )
        for cfg in deal_models:
            candidates += list(cfg.replenishments.all())
        candidates += list(
            Replenishment.objects.filter(items__configuration__in=deal_models).distinct()
        )
        chained_contract = configuration.active_contract
        if chained_contract is not None:
            models_on_contract = (
                chained_contract.items.exclude(configuration__isnull=True)
                .values_list('configuration_id', flat=True).distinct()
            )
            if len(models_on_contract) <= 1:
                candidates += list(chained_contract.replenishments.all())
    if contract is not None:
        candidates += list(contract.replenishments.all())
    return next((rep for rep in candidates if rep.is_open), None)


def _require_paid_chain(configuration):
    """YANGI-OQIM B4: ta'minot va yig'ish faqat boshlang'ich to'lovdan keyin.

    Zanjir endi `CFG → SHT → pul → mol`: pul kelmaguncha mol buyurtma
    qilinmaydi va yig'ilmaydi. Shartnoma rad etilgan/bekor qilingan bo'lsa —
    zanjir to'xtagan, boshqa matn bilan 400.
    """
    from rest_framework.exceptions import ValidationError

    from apps.sales.models import Contract

    # 12-§2 (C): ikkinchi model bo'lsa `active_contract` qator orqali ham
    # topadi; lekin bu yerda rad/bekor qilingan holatni ham ko'rish kerak
    # (xabar aniq bo'lsin), shuning uchun fallback keng
    contract = (
        configuration.contracts.order_by('-id').first()
        or configuration.active_contract
    )
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


def finalize_configuration(configuration, user, *, act=None, client=None):
    """Yakunlash (#4/§11.1) — shartlari: `approved` + yig'ilgan + ACT.

    16-to'plam: bu funksiya avval to'g'ridan-to'g'ri view'da yozilgan edi;
    `deal_finalize` (16-§A2) ham xuddi shu yo'ldan o'tishi kerak bo'lgani
    uchun bu yerga — servis qatlamiga — ko'chirildi. Xulq bitta belgigacha
    o'zgarmagan: `act`/`client` allaqachon resolve qilingan obyekt sifatida
    keladi (id → instance — view'ning ishi), bu yerda faqat biznes qoidasi.
    """
    from django.db.transaction import atomic
    from rest_framework.exceptions import ValidationError

    from apps.configurator.models import Configuration

    if configuration.status != Configuration.Status.APPROVED:
        raise ValidationError({
            'detail': (
                'Avval texnik yechim tasdiqlansin: engineer submit -> '
                'sales approve — shundan keyin yakunlanadi.'
            ),
        })
    if not configuration.assembled_at:
        raise ValidationError({
            'detail': "Avval mahsulot yig'ilsin (assemble) — yakunlash tayyor mahsulot bilan bo'ladi.",
        })
    if act is not None:
        configuration.act = act
    if not configuration.act:
        # 14-§7 (1): savdodagi boshqa modelga ACT allaqachon biriktirilgan
        # bo'lsa — ikkinchi modelni yakunlaganda uni qayta tanlamaydi
        request_obj = _owning_request(configuration)
        if deal_has_multiple_models(request_obj):
            sibling_act = next(
                (
                    cfg.act for cfg in _deal_models_for_request(request_obj)
                    if cfg.act_id and cfg.id != configuration.id
                ),
                None,
            )
            if sibling_act:
                configuration.act = sibling_act
    if not configuration.act:
        raise ValidationError({'detail': 'Yakunlash uchun ACT biriktirilishi shart.'})

    no_price = configuration.items_without_price
    if no_price:
        raise ValidationError({
            'detail': 'Narxi kiritilmagan butlovchilar bor.',
            'items': [item.component.name for item in no_price],
        })

    variant_moved = False
    with atomic():
        if client and not configuration.client_id:
            configuration.client = client
        configuration.status = Configuration.Status.READY
        configuration.save()

        from apps.core.services import resolve_notifications

        resolve_notifications('Configuration', configuration.pk, user=user)

        from apps.inventory.services import (
            sync_configuration_reservations,
            sync_contract_reservations,
        )

        # YANGI OQIM: shartnoma allaqachon bor (B1, approve'da ochilgan).
        # B6: qatordagi bazaviy model yig'ilgan VARIANTGA ko'chadi — son va
        # narx tegilmaydi, faqat SKU aniqlashadi (12-§2 C: qator
        # `configuration` FK orqali topiladi — bir nechta model bo'lsa ham to'g'ri)
        contract = configuration.active_contract
        if contract and configuration.variant_id:
            variant_moved = bool(
                contract.items.filter(configuration=configuration)
                .update(product=configuration.variant),
            )
        # B7: pul allaqachon kelgan bo'lsa zanjir yopildi — sold
        if contract and contract.status in ('active', 'completed'):
            configuration.status = Configuration.Status.SOLD
            configuration.save()

        sync_configuration_reservations(configuration)
        if contract:
            sync_contract_reservations(contract)

    return configuration, contract, variant_moved


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
    # (12-§2 C: ikkinchi model bo'lsa ham `active_contract` qator orqali topadi)
    own_contract = configuration.active_contract
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


def take_request(request_obj, user, base_product=None, warehouse=None, mode=None, line_modes=None):
    """Engineer zayavkani ishga oladi — chernovik konfiguratsiya avtomatik ochiladi.

    Bazaviy model: so'rov tanasidagi `base_product` > zayavkada yozilgani.
    Ikkalasi ham bo'lmasa 400 — konfiguratsiya modelsiz yaratilmaydi.

    12-§2 (B2): bitta amal — agar zayavkada QO'SHIMCHA MODEL qatorlari
    bo'lsa (`ConfigurationRequestLine.Kind.MODEL`), ularga ham shu yerda,
    bitta ishga olishda, alohida chernovik ochiladi. `line_modes` —
    `{line_id: 'build'|'modify'}`, har biriga alohida rejim; berilmasa
    umumiy `mode` (yoki BUILD) qo'llanadi. TOVAR qatorlariga (`Kind.ITEM`)
    konfiguratsiya kerak emas — ular shartnoma ochilganda to'g'ridan qatorga aylanadi.
    """
    from django.db.transaction import atomic
    from rest_framework.exceptions import PermissionDenied, ValidationError

    from apps.configurator.models import Configuration, ConfigurationRequest, ConfigurationRequestLine
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
    from apps.inventory.services import sync_configuration_reservations

    line_modes = line_modes or {}
    used_warehouse = warehouse or request_obj.warehouse or main_warehouse()

    with atomic():
        configuration = Configuration.objects.create(
            base_product=base_product,
            client=request_obj.client,
            warehouse=used_warehouse,
            mode=mode or Configuration.Mode.BUILD,
            # #3: mijoz nechta so'ragani zayavkadan ko'chadi (engineer
            # chernovikda o'zgartira oladi)
            quantity=request_obj.quantity,
            note=f'{request_obj.number}: {request_obj.text}',
            created_by=user,
        )
        copy_factory_spec(configuration)
        # §11.4: chernovik butlovchilarni "Rejada" deb belgilaydi (yumshoq bron)
        sync_configuration_reservations(configuration)

        request_obj.status = ConfigurationRequest.Status.IN_PROGRESS
        request_obj.taken_by = user
        request_obj.configuration = configuration
        request_obj.save()

        # 12-§2 (B2): qo'shimcha MODEL qatorlari — har biriga o'z chernovigi
        for line in request_obj.lines.filter(
            kind=ConfigurationRequestLine.Kind.MODEL, configuration__isnull=True,
        ):
            if line.base_product.kind != Product.Kind.MACHINE:
                raise ValidationError({
                    'detail': (
                        f'{line.base_product.name}: model turidagi qator faqat '
                        "tayyor model bo'lishi mumkin — tovar bo'lsa `item` turini tanlang."
                    ),
                })
            line_configuration = Configuration.objects.create(
                base_product=line.base_product,
                client=request_obj.client,
                warehouse=used_warehouse,
                mode=line_modes.get(line.id) or line_modes.get(str(line.id)) or Configuration.Mode.BUILD,
                quantity=line.quantity,
                note=f'{request_obj.number}: {line.text or line.base_product.name}',
                created_by=user,
            )
            copy_factory_spec(line_configuration)
            sync_configuration_reservations(line_configuration)
            line.configuration = line_configuration
            line.save(update_fields=['configuration'])

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

    14-§6: ko'p modelli savdoda BITTA hisob — savdodagi barcha (allaqachon
    tasdiqlangan) modellarning yetishmovchiligi shu bitta `Replenishment`ga
    qo'yiladi, har bir qator `ReplenishmentItem.configuration` bilan qaysi
    modelniki ekanini bildiradi. `Replenishment.configuration` — savdoning
    ASOSIY modeli (12-§2 B dagi asimmetriyaning o'zi).
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

    request_obj = _owning_request(configuration)
    is_deal = deal_has_multiple_models(request_obj)
    deal_models = _deal_models_for_request(request_obj) if is_deal else [configuration]
    primary_configuration = (
        request_obj.configuration if (is_deal and request_obj.configuration_id) else configuration
    )

    # 14-§6 (4): savdodagi istalgan modelda ochiq TLD bo'lsa — undan yangisi
    # ochilmaydi. 11-§1: shartnoma eshigidan ochilgani ham hisobga kiradi
    existing = chain_open_replenishment(configuration=configuration)

    # Bitta modelli zanjir — eski xulq o'zgarishsiz: ochiq hisob bo'lsa,
    # holatidan qat'i nazar, yangisi ochilmaydi (qo'shish ham yo'q).
    if not is_deal and existing:
        raise ValidationError({
            'detail': (
                f'{configuration.number} uchun {existing.number} hisobi allaqachon '
                f'ochilgan ({existing.get_status_display()}) — yangisini ochish shart emas.'
            ),
            'replenishment': existing.pk,
        })

    # 14-§6 (5): ko'p modelli savdoda — ochiq TLD hali tasdiq yo'liga
    # chiqmagan bo'lsa, yangi yetishmovchilik O'SHA hisobga qo'shiladi; aks
    # holda (pending_admin va undan keyin) admin ko'rgan raqam jimgina
    # o'zgarib qolmasin — u tegilmay qoladi va YANGI TLD ochishga ruxsat
    # beriladi (bloklanmaydi, faqat mavjudi endi "manba" bo'lmay qoladi).
    addable = {
        Replenishment.Status.DRAFT, Replenishment.Status.PENDING_SALES,
        Replenishment.Status.PENDING_BUGALTER, Replenishment.Status.REJECTED,
    }
    if is_deal and existing and existing.status not in addable:
        existing = None

    # 3-to'plam §1: ro'yxat `required_from_stock` dan — modify'da yetishmagan
    # BAZAVIY MODEL ham TLD ga tushadi, o'zgarmagan qismlar esa tushmaydi.
    # Faqat ALLAQACHON tasdiqlangan modellar hisobga kiradi — hali sales
    # ko'rigidagi model o'z navbatida (keyinroq) shu TLDga qo'shiladi.
    missing_by_model = [
        (cfg, cfg.missing_items) for cfg in deal_models
        if cfg.status == Configuration.Status.APPROVED and cfg.missing_items
    ]
    if not missing_by_model:
        raise ValidationError({
            'detail': "Hammasi omborda yetarli — buyurtmachiga yuborish shart emas.",
        })

    # §4.3 (SIDEBAR-VA-EGALIK): zayavka egasi (sales) bir marta topilib hisobga
    # yozib qo'yiladi — bildirishnoma va pending_sales bosqichi shu odamniki
    owner_sales = request_obj.created_by if request_obj else None

    with atomic():
        if existing:
            replenishment = existing
            added_rows = []
            for cfg, missing in missing_by_model:
                for row in missing:
                    already = replenishment.items.filter(
                        product=row['product'], configuration=cfg,
                    ).exists()
                    if already:
                        continue
                    ReplenishmentItem.objects.create(
                        replenishment=replenishment,
                        product=row['product'],
                        quantity=row['shortage'],
                        unit_price=row['product'].cost_price or 0,
                        configuration=cfg,
                        note=f'{cfg.number} konfiguratsiyasi uchun',
                    )
                    added_rows.append(row)
            # Hammasi allaqachon shu hisobda bo'lsa ham — bu xato emas,
            # takroriy so'rov: mavjudini o'zgarishsiz qaytaramiz (201).
            names = ', '.join(row['product'].name for row in added_rows)
            title = f"{configuration.number}: {existing.number}ga qo'shimcha qator"
        else:
            replenishment = Replenishment.objects.create(
                warehouse=configuration.warehouse or main_warehouse(),
                configuration=primary_configuration,
                owner_sales=owner_sales,
                note=(
                    f"{request_obj.number}: yetishmayotgan butlovchilar"
                    if is_deal else f"{configuration.number} uchun yetishmayotgan butlovchilar"
                ),
                created_by=user,
            )
            for cfg, missing in missing_by_model:
                for row in missing:
                    ReplenishmentItem.objects.create(
                        replenishment=replenishment,
                        product=row['product'],
                        quantity=row['shortage'],
                        unit_price=row['product'].cost_price or 0,
                        configuration=cfg if is_deal else None,
                        note=f'{cfg.number} konfiguratsiyasi uchun',
                    )
            names = ', '.join(
                row['product'].name for _cfg, missing in missing_by_model for row in missing
            )
            title = f"{configuration.number}: omborda yo'q butlovchilar ({replenishment.number})"

    # Hovuz: buyurtmachi (ish unga keldi) va bugalter (oldindan biladi).
    # Sales — hovuz EMAS (§4.2): faqat zayavka egasi; egasi aniqlanmasa
    # (ZVK'siz konfiguratsiya) barcha sales'ga tushadi — xabar yo'qolmasin.
    if names:
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
                title=title,
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

    from apps.inventory.services import release_reservations

    # 12-§2 (B): asosiy model + qo'shimcha MODEL qatorlarining hammasi —
    # yarim tarkiblar egasiz qolib, keyingi engineerni chalg'itmasin
    configurations = [request_obj.configuration] if request_obj.configuration else []
    configurations += [
        line.configuration for line in request_obj.lines.select_related('configuration')
        if line.configuration_id
    ]
    for configuration in configurations:
        if configuration.status not in {
            Configuration.Status.CANCELLED, Configuration.Status.SOLD,
        }:
            configuration.status = Configuration.Status.CANCELLED
            configuration.cancel_reason = comment  # 8-to'plam §4
            configuration.save()
            release_reservations(
                configuration=configuration, user=user,
                note=f'{request_obj.number} hovuzga qaytarildi: {comment}',
            )

    request_obj.lines.filter(configuration__isnull=False).update(configuration=None)
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
        # 12-§2 (B): qo'shimcha model qatori bo'lsa qator orqali ham qidiriladi
        request_obj = _owning_request(configuration)
    if configuration is not None and contract is None:
        # 12-§2 (C): ikkinchi model bo'lsa `active_contract` qator orqali topadi
        contract = configuration.active_contract or (
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

        # 12-§2 (B): qo'shimcha MODEL qatorlarining chernoviklari ham —
        # butun zanjir to'xtaganda ular egasiz yarim tarkib bo'lib qolmasin
        if request_obj is not None:
            for line in request_obj.lines.select_related('configuration'):
                extra_config = line.configuration
                if extra_config is None or extra_config.status == Configuration.Status.CANCELLED:
                    continue
                extra_config.status = Configuration.Status.CANCELLED
                extra_config.cancel_reason = reason
                extra_config.save()
                release_reservations(configuration=extra_config, user=user, note=reason)

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
