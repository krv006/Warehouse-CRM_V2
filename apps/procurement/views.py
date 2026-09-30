from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import (
    FinanceAccess,
    ImportCostAccess,
    PriceRequestAccess,
    ProcurementAccess,
    ProcurementApprovalAccess,
    ProcurementSharedAccess,
)
from apps.core.mixins import BaseModelViewSet
from apps.core.models import ActivityLog
from apps.inventory.models import Product, Warehouse
from apps.procurement.models import (
    ImportCostSheet,
    PriceRequest,
    PriceRequestLine,
    Replenishment,
    ReplenishmentApproval,
    ReplenishmentEvent,
    ReplenishmentItem,
)
from apps.procurement.serializers import (
    ImportCostSheetSerializer,
    PriceRequestLineSerializer,
    PriceRequestSerializer,
    ReplenishmentApprovalSerializer,
    ReplenishmentEventSerializer,
    ReplenishmentItemSerializer,
    ReplenishmentSerializer,
)
from apps.procurement.services import (
    add_event,
    answer_price_request_line,
    approve,
    build_from_low_stock,
    cancel_import_sheet,
    cancel_price_request,
    change_import_sheet_quantity,
    fill_customs_section,
    fill_goods_section,
    fill_logistics_section,
    fill_price_request_customs,
    fill_price_request_logistics,
    low_stock_products,
    mark_price_request_line_imported,
    open_import_sheet,
    pay,
    receive,
    reject,
    return_import_sheet,
    send_price_request_line_to_customs,
    submit,
)

# Tasdiqlash zanjiri: sales (mijoz roziligi) -> bugalter -> admin — bosqichni servis tekshiradi
APPROVAL_ACTIONS = {'approve', 'reject'}

# Faqat bugalter/admin bajaradigan amallar
BUGALTER_ACTIONS = {'pay'}

# Buyurtmachi ham, bugalter ham bajaradi — rolni servis tekshiradi
SHARED_ACTIONS = {'receive', 'add_event'}


class ReplenishmentViewSet(BaseModelViewSet):
    """Omborni to'ldirish: buyurtmachi -> bugalter -> admin -> to'lov -> ombor."""

    queryset = (
        Replenishment.objects
        .select_related('warehouse', 'debt', 'created_by')
        .prefetch_related('items__product', 'approvals__decided_by', 'events__created_by')
        .all()
    )
    serializer_class = ReplenishmentSerializer
    permission_classes = [ProcurementAccess]
    search_fields = ['number', 'supplier']
    filterset_fields = [
        'status', 'warehouse', 'currency', 'configuration', 'contract',
        'created_by', 'owner_sales',
    ]
    ordering_fields = ['created_at', 'number', 'created_by']

    def get_queryset(self):
        """EGALIK §3.2 + TOPSHIRIQ #1: sales O'Z hisobini butun yo'l davomida
        ko'radi (tasdiqlagach ham — mijozga "qachon keladi?"ga javob berishi
        kerak); boshqa sales'nikini ko'rmaydi — egalik saqlanadi. Egasiz hisob
        faqat mijoz roziligi bosqichida ko'rinadi (oddiy ombor to'ldirishlari
        sales'ga tegishli emas). Amal huquqi o'zgarmagan: approve/reject
        baribir faqat pending_sales'da ishlaydi — qolganida faqat kuzatadi."""
        from django.db.models import Q

        qs = super().get_queryset()
        user = self.request.user
        if user.is_admin or user.is_bugalter or user.is_supplier:
            return qs
        if user.is_sales:
            return qs.filter(
                Q(owner_sales=user)
                | Q(owner_sales__isnull=True,
                    status=Replenishment.Status.PENDING_SALES),
            )
        return qs.none()

    def get_permissions(self):
        if self.action in APPROVAL_ACTIONS:
            return [ProcurementApprovalAccess()]
        if self.action in BUGALTER_ACTIONS:
            return [FinanceAccess()]
        if self.action in SHARED_ACTIONS:
            return [ProcurementSharedAccess()]
        return super().get_permissions()

    def low_stock(self, request):
        """GET /replenishments/low-stock/ — yetishmayotgan mahsulotlar ro'yxati."""
        warehouse = Warehouse.objects.filter(pk=request.query_params.get('warehouse')).first()
        return Response([
            {
                'id': product.id,
                'sku': product.sku,
                'name': product.name,
                'total_stock': product.current_stock,
                'reorder_level': product.reorder_level,
                'needed': max(product.reorder_level - product.current_stock, 1),
                'cost_price': product.cost_price,
            }
            for product in low_stock_products(warehouse)
        ])

    def from_low_stock(self, request):
        """POST /replenishments/from-low-stock/ — ro'yxatdan hisob shakllantiradi.

        Biznesda bitta ombor — `warehouse` yuborilmasa yagona ombor olinadi.
        """
        from apps.inventory.services import main_warehouse

        warehouse = Warehouse.objects.filter(pk=request.data.get('warehouse')).first()
        if not warehouse:
            warehouse = main_warehouse()
        replenishment = build_from_low_stock(
            warehouse, request.user, request.data.get('supplier', ''),
        )
        self.log_action(ActivityLog.Action.CREATE, replenishment, 'Yetishmovchilikdan yaratildi')
        return Response(self.get_serializer(replenishment).data)

    def submit(self, request, pk=None):
        """POST /replenishments/{id}/submit/ — tekshiruvga yuborish.

        Konfiguratsiyadan (mijoz buyurtmasidan) ochilgan hisob avval sales'ga,
        oddiy to'ldirish to'g'ridan-to'g'ri bugalterga boradi.
        """
        replenishment = submit(self.get_object(), request.user)
        self.log_action(
            ActivityLog.Action.UPDATE, replenishment,
            replenishment.get_status_display(),
        )
        return Response(self.get_serializer(replenishment).data)

    def approve(self, request, pk=None):
        """POST /replenishments/{id}/approve/ — sales (mijozniki bo'lsa), bugalter, admin."""
        replenishment = approve(
            self.get_object(), request.user, request.data.get('comment', ''),
        )
        self.log_action(
            ActivityLog.Action.APPROVE, replenishment, replenishment.get_status_display(),
        )
        return Response(self.get_serializer(replenishment).data)

    def reject(self, request, pk=None):
        """POST /replenishments/{id}/reject/ — qaytarish."""
        replenishment = reject(
            self.get_object(), request.user, request.data.get('comment', ''),
        )
        self.log_action(ActivityLog.Action.REJECT, replenishment, request.data.get('comment', ''))
        return Response(self.get_serializer(replenishment).data)

    def pay(self, request, pk=None):
        """POST /replenishments/{id}/pay/ — to'lov; pul yetmasa qarzga o'tadi."""
        debt_amount = request.data.get('debt_amount')
        replenishment = pay(
            self.get_object(),
            request.user,
            debt_amount=None if debt_amount is None else debt_amount,
        )
        self.log_action(
            ActivityLog.Action.UPDATE, replenishment,
            f"To'landi: {replenishment.paid_amount}, qarz: {replenishment.debt or 0}",
        )
        return Response(self.get_serializer(replenishment).data)

    def add_event(self, request, pk=None):
        """POST /replenishments/{id}/events/ — bosqich qo'shish (bojxona va h.k.)."""
        replenishment = self.get_object()
        stage = request.data.get('stage')
        if stage not in ReplenishmentEvent.Stage.values:
            raise ValidationError({'stage': f'Mumkin qiymatlar: {ReplenishmentEvent.Stage.values}'})
        event = add_event(
            replenishment, request.user,
            stage=stage, comment=request.data.get('comment', ''),
        )
        self.log_action(ActivityLog.Action.CREATE, event)
        return Response(ReplenishmentEventSerializer(event).data)

    def receive(self, request, pk=None):
        """POST /replenishments/{id}/receive/ — omborga kirim qilish."""
        replenishment = receive(self.get_object(), request.user)
        self.log_action(ActivityLog.Action.UPDATE, replenishment, 'Omborga kirim qilindi')
        return Response(self.get_serializer(replenishment).data)

    def timeline(self, request, pk=None):
        """GET /replenishments/{id}/timeline/ — bosqichlar va qarz muddati."""
        replenishment = self.get_object()
        return Response({
            'number': replenishment.number,
            'status': replenishment.status,
            'total_amount': replenishment.total_amount,
            'paid_amount': replenishment.paid_amount,
            'events': ReplenishmentEventSerializer(
                replenishment.events.all(), many=True,
            ).data,
            'debt': {
                'amount': replenishment.debt.amount if replenishment.debt else 0,
                'deadline': replenishment.debt.deadline if replenishment.debt else None,
                **replenishment.debt_progress,
            },
        })


class ReplenishmentItemViewSet(BaseModelViewSet):
    """Hisob qatorlari. Admin istalgan paytda, buyurtmachi faqat qoralamada tahrirlaydi."""

    queryset = ReplenishmentItem.objects.select_related('replenishment', 'product').all()
    serializer_class = ReplenishmentItemSerializer
    permission_classes = [ProcurementAccess]
    filterset_fields = ['replenishment', 'product']

    def get_queryset(self):
        from django.db.models import Q

        qs = super().get_queryset()
        user = self.request.user
        if user.is_sales:
            # TOPSHIRIQ #1: o'z hisobining qatorlari butun yo'l davomida ochiq
            return qs.filter(
                Q(replenishment__owner_sales=user)
                | Q(replenishment__owner_sales__isnull=True,
                    replenishment__status=Replenishment.Status.PENDING_SALES),
            )
        return qs

    def _check_editable(self, item):
        user = self._current_user()
        if user and user.is_admin:
            return
        editable = {Replenishment.Status.DRAFT, Replenishment.Status.REJECTED}
        if item.replenishment.status not in editable:
            raise PermissionDenied(
                'Hisob tekshiruvga yuborilgan — faqat admin tahrirlay oladi.',
            )

    def perform_update(self, serializer):
        self._check_editable(serializer.instance)
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        self._check_editable(instance)
        super().perform_destroy(instance)


class ReplenishmentApprovalViewSet(BaseModelViewSet):
    """Tasdiqlash tarixi — faqat o'qish."""

    queryset = ReplenishmentApproval.objects.select_related(
        'replenishment', 'decided_by',
    ).all()
    serializer_class = ReplenishmentApprovalSerializer
    permission_classes = [ProcurementAccess]
    filterset_fields = ['replenishment', 'step', 'decision']


class ReplenishmentEventViewSet(BaseModelViewSet):
    """Yetkazib berish bosqichlari — faqat o'qish (qo'shish action orqali)."""

    queryset = ReplenishmentEvent.objects.select_related(
        'replenishment', 'created_by',
    ).all()
    serializer_class = ReplenishmentEventSerializer
    permission_classes = [ProcurementAccess]
    filterset_fields = ['replenishment', 'stage']


# 24-to'plam: bo'lim ichida kim qaysi maydonni yozishi servis darajasida
# tekshiriladi (§6.3) — bu amallar uchun ViewSet faqat autentifikatsiyani
# talab qiladi, aniq rolni `fill_*`/`open`/`return_sheet`/`cancel`/
# `change_quantity` servis funksiyalarining o'zi tekshiradi.
IMPORT_SHEET_SERVICE_ACTIONS = {
    'open', 'fill_goods', 'fill_logistics', 'fill_customs',
    'return_sheet', 'cancel', 'change_quantity',
}


class ImportCostSheetViewSet(BaseModelViewSet):
    """24-to'plam: import tannarx varaqasi — tovar → logistika → bojxona.

    Generic PATCH/PUT/DELETE yo'q — har bir bo'lim faqat o'z servis
    funksiyasi orqali to'ldiriladi (§6.3: ketma-ketlik shu yerda ham
    qat'iy). §4.1: engineer bu bo'limni umuman ochmaydi (`ImportCostAccess`
    ro'yxatida yo'q — 403); logist/deklarant/buyurtmachi/bugalter rol
    bo'ylab hammasini ko'radi (egasi bo'yicha emas, §7 case 17).
    """

    queryset = ImportCostSheet.objects.select_related(
        'product', 'configuration', 'goods_filled_by',
        'logistics_filled_by', 'customs_filled_by', 'created_by',
    ).all()
    serializer_class = ImportCostSheetSerializer
    permission_classes = [ImportCostAccess]
    filterset_fields = ['status', 'product', 'configuration']
    ordering_fields = ['created_at', 'number']

    def get_permissions(self):
        if self.action in IMPORT_SHEET_SERVICE_ACTIONS:
            return [IsAuthenticated()]
        return super().get_permissions()

    def open(self, request):
        """POST /import-cost-sheets/open/ — §6.4: Engineer/buyurtmachi/admin."""
        product = Product.objects.filter(pk=request.data.get('product')).first()
        if product is None:
            raise ValidationError({'product': 'Mahsulot topilmadi.'})
        configuration = None
        if request.data.get('configuration'):
            from apps.configurator.models import Configuration

            configuration = Configuration.objects.filter(
                pk=request.data['configuration'],
            ).first()
        sheet = open_import_sheet(
            product, request.user,
            quantity=request.data.get('quantity', 1),
            configuration=configuration,
        )
        self.log_action(ActivityLog.Action.CREATE, sheet, f'{sheet.number} ochildi')
        return Response(self.get_serializer(sheet).data, status=201)

    def fill_goods(self, request, pk=None):
        """POST /import-cost-sheets/{id}/fill-goods/ — A. Buyurtmachi."""
        sheet = fill_goods_section(
            self.get_object(), request.user,
            currency=request.data.get('currency', 'USD'),
            goods_price=request.data.get('goods_price'),
            exchange_rate=request.data.get('exchange_rate'),
            origin_country=request.data.get('origin_country', ''),
        )
        self.log_action(ActivityLog.Action.UPDATE, sheet, f'{sheet.number}: tovar ma\'lumoti to\'ldirildi')
        return Response(self.get_serializer(sheet).data)

    def fill_logistics(self, request, pk=None):
        """POST /import-cost-sheets/{id}/fill-logistics/ — B. Logist."""
        sheet = fill_logistics_section(
            self.get_object(), request.user,
            logistics_total=request.data.get('logistics_total'),
            note=request.data.get('note', ''),
        )
        self.log_action(ActivityLog.Action.UPDATE, sheet, f'{sheet.number}: logistika narxi kiritildi')
        return Response(self.get_serializer(sheet).data)

    def fill_customs(self, request, pk=None):
        """POST /import-cost-sheets/{id}/fill-customs/ — C. Deklarant, hisobni yopadi."""
        data = request.data
        sheet = fill_customs_section(
            self.get_object(), request.user,
            tnved_code=data.get('tnved_code', ''),
            freight_to_border=data.get('freight_to_border'),
            duty_percent=data.get('duty_percent', 0),
            duty_amount=data.get('duty_amount', 0),
            excise_amount=data.get('excise_amount', 0),
            vat_percent=data.get('vat_percent', 12),
            customs_fee=data.get('customs_fee'),
            certificate_cost=data.get('certificate_cost', 0),
            laboratory_cost=data.get('laboratory_cost', 0),
            declarant_fee=data.get('declarant_fee', 0),
            note=data.get('note', ''),
        )
        self.log_action(ActivityLog.Action.UPDATE, sheet, f'{sheet.number}: bojxona hisobi yopildi')
        return Response(self.get_serializer(sheet).data)

    def return_sheet(self, request, pk=None):
        """POST /import-cost-sheets/{id}/return/ — logist/deklarant orqaga qaytaradi."""
        sheet = return_import_sheet(self.get_object(), request.user, request.data.get('comment', ''))
        self.log_action(ActivityLog.Action.UPDATE, sheet, f'{sheet.number} qaytarildi')
        return Response(self.get_serializer(sheet).data)

    def cancel(self, request, pk=None):
        """POST /import-cost-sheets/{id}/cancel/ — admin yoki ochgan odam."""
        sheet = cancel_import_sheet(self.get_object(), request.user, request.data.get('reason', ''))
        self.log_action(ActivityLog.Action.UPDATE, sheet, f'{sheet.number} bekor qilindi')
        return Response(self.get_serializer(sheet).data)

    def change_quantity(self, request, pk=None):
        """POST /import-cost-sheets/{id}/change-quantity/ — §7 case 6."""
        sheet = change_import_sheet_quantity(
            self.get_object(), request.user, request.data.get('quantity'),
        )
        self.log_action(ActivityLog.Action.UPDATE, sheet, f'{sheet.number}: miqdor o\'zgartirildi')
        return Response(self.get_serializer(sheet).data)


class PriceRequestViewSet(BaseModelViewSet):
    """28-§1: narx so'rovi — hujjatning o'zi faqat o'qish + bekor qilish
    uchun; bo'limlarni to'ldirish `PriceRequestLineViewSet` orqali."""

    queryset = PriceRequest.objects.select_related(
        'configuration', 'created_by',
    ).prefetch_related('lines__product').all()
    serializer_class = PriceRequestSerializer
    permission_classes = [PriceRequestAccess]
    filterset_fields = ['status', 'configuration']
    ordering_fields = ['created_at', 'number']

    def cancel(self, request, pk=None):
        """POST /price-requests/{id}/cancel/ — admin yoki ochgan odam."""
        price_request = cancel_price_request(
            self.get_object(), request.user, request.data.get('reason', ''),
        )
        self.log_action(ActivityLog.Action.UPDATE, price_request, f'{price_request.number} bekor qilindi')
        return Response(self.get_serializer(price_request).data)


# 28-§2: rolning o'zi servis darajasida tekshiriladi (`_require`) —
# ViewSet bu amallar uchun faqat autentifikatsiyani talab qiladi.
PRICE_REQUEST_LINE_SERVICE_ACTIONS = {
    'fill_logistics', 'fill_customs', 'send_to_customs', 'mark_imported', 'answer',
}


class PriceRequestLineViewSet(BaseModelViewSet):
    """28-§1/§2: bitta mahsulot — logist/deklarant/buyurtmachi shu yerda
    o'z qismini bajaradi, bir-birining raqamini ko'rmaydi (serializer)."""

    queryset = PriceRequestLine.objects.select_related('request', 'product').all()
    serializer_class = PriceRequestLineSerializer
    permission_classes = [PriceRequestAccess]

    def get_permissions(self):
        if self.action in PRICE_REQUEST_LINE_SERVICE_ACTIONS:
            return [IsAuthenticated()]
        return super().get_permissions()

    def fill_logistics(self, request, pk=None):
        """POST /price-request-lines/{id}/fill-logistics/ — Logist."""
        line = fill_price_request_logistics(
            self.get_object(), request.user,
            logistics_total=request.data.get('logistics_total'),
            freight_to_border=request.data.get('freight_to_border'),
            note=request.data.get('note', ''),
        )
        self.log_action(ActivityLog.Action.UPDATE, line, f'{line.request.number}: logistika narxi kiritildi')
        return Response(self.get_serializer(line).data)

    def fill_customs(self, request, pk=None):
        """POST /price-request-lines/{id}/fill-customs/ — Deklarant."""
        data = request.data
        line = fill_price_request_customs(
            self.get_object(), request.user,
            tnved_code=data.get('tnved_code', ''),
            duty_percent=data.get('duty_percent', 0),
            duty_amount=data.get('duty_amount', 0),
            excise_amount=data.get('excise_amount', 0),
            customs_fee=data.get('customs_fee'),
            certificate_cost=data.get('certificate_cost', 0),
            laboratory_cost=data.get('laboratory_cost', 0),
            declarant_fee=data.get('declarant_fee', 0),
            note=data.get('note', ''),
        )
        self.log_action(ActivityLog.Action.UPDATE, line, f'{line.request.number}: bojxona hisobi kiritildi')
        return Response(self.get_serializer(line).data)

    def send_to_customs(self, request, pk=None):
        """POST /price-request-lines/{id}/send-to-customs/ — §3 case 4."""
        line = send_price_request_line_to_customs(self.get_object(), request.user)
        self.log_action(ActivityLog.Action.UPDATE, line, f'{line.request.number}: deklarantga yuborildi')
        return Response(self.get_serializer(line).data)

    def mark_imported(self, request, pk=None):
        """POST /price-request-lines/{id}/mark-imported/ — buyurtmachi belgilaydi."""
        line = mark_price_request_line_imported(self.get_object(), request.user)
        self.log_action(ActivityLog.Action.UPDATE, line, f'{line.request.number}: import deb belgilandi')
        return Response(self.get_serializer(line).data)

    def answer(self, request, pk=None):
        """POST /price-request-lines/{id}/answer/ — Buyurtmachi yakunlaydi."""
        data = request.data
        line = answer_price_request_line(
            self.get_object(), request.user,
            cost_price=data.get('cost_price'),
            currency=data.get('currency'),
            goods_price=data.get('goods_price'),
            exchange_rate=data.get('exchange_rate'),
        )
        self.log_action(ActivityLog.Action.UPDATE, line, f'{line.request.number}: tannarx berildi')
        return Response(self.get_serializer(line).data)
