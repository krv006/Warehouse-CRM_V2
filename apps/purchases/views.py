from rest_framework.response import Response

from apps.accounts.permissions import PurchaseAccess
from apps.core.mixins import BaseModelViewSet
from apps.core.models import ActivityLog
from apps.purchases.models import Purchase, PurchaseItem, PurchaseDocument
from apps.purchases.serializers import (
    PurchaseSerializer,
    PurchaseItemSerializer,
    PurchaseDocumentSerializer,
)
from apps.purchases.services import receive_purchase


class PurchaseViewSet(BaseModelViewSet):
    """Kirim: O'zbekiston ichidan, import va ustav."""

    queryset = (
        Purchase.objects
        .select_related('warehouse', 'contract', 'created_by')
        .prefetch_related('items__product', 'documents__uploaded_by')
        .all()
    )
    serializer_class = PurchaseSerializer
    permission_classes = [PurchaseAccess]
    search_fields = ['number', 'supplier', 'invoice_number']
    filterset_fields = ['type', 'status', 'warehouse', 'currency']
    ordering_fields = ['created_at', 'ordered_at', 'expected_at']

    def receive(self, request, pk=None):
        """POST /purchases/{id}/receive/ — omborga kirim, kassaga chiqim."""
        purchase = receive_purchase(self.get_object(), request.user)
        self.log_action(ActivityLog.Action.UPDATE, purchase, 'Kirim qabul qilindi')
        return Response(self.get_serializer(purchase).data)

    def timeline(self, request, pk=None):
        """GET /purchases/{id}/timeline/ — import kunlarining line chart ma'lumoti."""
        purchase = self.get_object()
        return Response({
            'number': purchase.number,
            'type': purchase.type,
            'status': purchase.status,
            **purchase.progress,
        })

    def in_transit(self, request):
        """GET /purchases/in-transit/ — yo'ldagi importlar."""
        purchases = self.filter_queryset(self.get_queryset()).filter(
            status__in=[Purchase.Status.ORDERED, Purchase.Status.IN_TRANSIT],
        )
        return Response([
            {
                'id': purchase.id,
                'number': purchase.number,
                'type': purchase.type,
                'supplier': purchase.supplier,
                'expected_at': purchase.expected_at,
                'days_left': purchase.days_left,
                'color': purchase.color,
            }
            for purchase in purchases
        ])


class PurchaseItemViewSet(BaseModelViewSet):
    queryset = PurchaseItem.objects.select_related('purchase', 'product').all()
    serializer_class = PurchaseItemSerializer
    permission_classes = [PurchaseAccess]
    filterset_fields = ['purchase', 'product']


class PurchaseDocumentViewSet(BaseModelViewSet):
    """Kirim hujjatlari — hujjatlar bilan bugalter ishlaydi (TZ 2.2, 8.2)."""

    queryset = PurchaseDocument.objects.select_related('purchase', 'uploaded_by').all()
    serializer_class = PurchaseDocumentSerializer
    permission_classes = [PurchaseAccess]
    filterset_fields = ['purchase', 'kind']

    def perform_create(self, serializer):
        document = serializer.save(uploaded_by=self._current_user())
        self.log_action(ActivityLog.Action.CREATE, document)
