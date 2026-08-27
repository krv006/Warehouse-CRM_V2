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
