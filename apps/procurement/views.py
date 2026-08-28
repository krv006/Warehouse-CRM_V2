from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.accounts.permissions import (
    FinanceAccess,
    ProcurementAccess,
    ProcurementSharedAccess,
)
from apps.core.mixins import BaseModelViewSet
from apps.core.models import ActivityLog
from apps.inventory.models import Warehouse
from apps.procurement.models import (
    Replenishment,
    ReplenishmentApproval,
    ReplenishmentEvent,
    ReplenishmentItem,
)
from apps.procurement.serializers import (
    ReplenishmentApprovalSerializer,
    ReplenishmentEventSerializer,
    ReplenishmentItemSerializer,
    ReplenishmentSerializer,
)
from apps.procurement.services import (
    add_event,
    approve,
    build_from_low_stock,
    low_stock_products,
    pay,
    receive,
    reject,
    submit,
)

# Bugalter/admin bajaradigan amallar
BUGALTER_ACTIONS = {'approve', 'reject', 'pay'}

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
    filterset_fields = ['status', 'warehouse', 'currency']
    ordering_fields = ['created_at', 'number']

    def get_permissions(self):
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
        """POST /replenishments/{id}/submit/ — bugalterga yuborish."""
        replenishment = submit(self.get_object(), request.user)
        self.log_action(ActivityLog.Action.UPDATE, replenishment, 'Bugalterga yuborildi')
        return Response(self.get_serializer(replenishment).data)

    def approve(self, request, pk=None):
        """POST /replenishments/{id}/approve/ — bugalter, so'ng admin."""
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
