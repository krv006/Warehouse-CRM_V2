from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.accounts.permissions import ProductPricingAccess, ProductSpecAccess
from apps.core.mixins import BaseModelViewSet
from apps.inventory.models import (
    Warehouse,
    Product,
    ProductSpec,
    Stock,
    StockMovement,
    StockReservation,
)
from apps.inventory.serializers import (
    WarehouseSerializer,
    ProductSerializer,
    ProductSpecSerializer,
    StockSerializer,
    StockMovementSerializer,
    StockReservationSerializer,
)


class WarehouseViewSet(ReadOnlyModelViewSet):
    """Omborlar — ma'lumotnoma, faqat o'qish uchun."""

    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer
    search_fields = ['name', 'address']
    filterset_fields = ['is_active']


class ProductViewSet(BaseModelViewSet):
    """Mahsulotlar katalogi.

    Yangi mahsulot alohida "qo'shish" oynasi orqali emas, Buyurtmachi
    to'ldirish buyurtmasiga qator qo'shganda katalogga tushadi (TZ 7) —
    shuning uchun POST/DELETE marshrutda yo'q. PATCH esa ochiq: admin va
    bugalter narx siyosatini yuritadi (`sale_price`, `reorder_level`,
    `is_active`, `cost_price`) — qolgan maydonlar o'zgarmaydi.
    """

    permission_classes = [ProductPricingAccess]

    queryset = (
        Product.objects
        .prefetch_related('stocks', 'specs__component')
        .all()
    )
    serializer_class = ProductSerializer
    search_fields = ['name', 'sku']
    filterset_fields = ['is_active', 'kind', 'base_model']
    ordering_fields = ['name', 'sale_price', 'created_at']

    def get_queryset(self):
        """10-to'plam §1: `?needs_price=true` — narxi KUTILAYOTGAN mahsulotlar.

        Ochiq konfiguratsiyada narxsiz qator sifatida turganlar — shunchaki
        `cost_price=0` emas (katalogda hech kim so'ramagan narxsiz yozuvlar
        bu ro'yxatni ko'mib tashlardi). Buyurtmachining doimiy ro'yxati:
        eslatma bir martalik signal, bu esa har doim ko'rinadi.
        """
        qs = super().get_queryset()
        if self.request.query_params.get('needs_price') in ('true', '1'):
            from apps.configurator.models import Configuration

            qs = qs.filter(
                configuration_items__unit_price=0,
                configuration_items__configuration__status__in=[
                    Configuration.Status.DRAFT,
                    Configuration.Status.PENDING_CLARIFICATION,
                    Configuration.Status.PENDING_SALES,
                ],
            ).distinct()
        return qs

    def perform_update(self, serializer):
        """YANGI-OQIM B2.3: narx kiritildi — kutayotgan konfiguratsiyalar uyg'onadi.

        Buyurtmachi (yoki bugalter) narxsiz mahsulotga narx qo'ysa: nol
        qatorlar to'ldiriladi, "narx kerak" eslatmasi yopiladi, sales'ga
        "narx keldi — mijoz bilan kelishing" xabari boradi.
        """
        had_price = bool(serializer.instance.stock_price)
        super().perform_update(serializer)
        if not had_price and serializer.instance.stock_price:
            from apps.configurator.services import price_arrived

            price_arrived(serializer.instance, self.request.user)


class ProductSpecViewSet(BaseModelViewSet):
    """Tayyor model tarkibi (ichidagi configlar).

    O'qish hammaga; yozish — **engineer va buyurtmachi** (admin):
    buyurtmachi tayyor modelni kirim qilganda tarkibini ham kiritadi,
    engineer configurator ishida yuritadi (TZ 6.1, 7).
    """

    permission_classes = [ProductSpecAccess]

    queryset = ProductSpec.objects.select_related('product', 'component').all()
    serializer_class = ProductSpecSerializer
    filterset_fields = ['product', 'component']


class StockViewSet(ReadOnlyModelViewSet):
    """Qoldiqlar — faqat Kirim va Chiqim orqali o'zgaradi (TZ 1-bo'lim)."""

    queryset = Stock.objects.select_related('product', 'warehouse').order_by('id')
    serializer_class = StockSerializer
    filterset_fields = ['product', 'warehouse']


class StockMovementViewSet(ReadOnlyModelViewSet):
    """Ombor harakatlari tarixi — jarayonlar tomonidan yoziladi."""

    queryset = StockMovement.objects.select_related('product', 'warehouse', 'created_by').all()
    serializer_class = StockMovementSerializer
    filterset_fields = ['product', 'warehouse', 'type', 'reason']


class StockReservationViewSet(BaseModelViewSet):
    """Bronlar (§11.4): jarayonlar avtomatik qo'yadi va bo'shatadi.

    O'qish — mahsulotni ko'ra oladigan har kim; qo'lda bo'shatish
    (`release`) — faqat admin, sabab majburiy va auditga tushadi.
    """

    queryset = (
        StockReservation.objects
        .select_related('product', 'warehouse', 'contract', 'configuration', 'released_by')
        .order_by('-id')
    )
    serializer_class = StockReservationSerializer
    filterset_fields = ['product', 'warehouse', 'kind', 'status', 'contract', 'configuration']

    def get_permissions(self):
        from apps.accounts.permissions import IsAdmin

        if self.action == 'release':
            return [IsAdmin()]
        return super().get_permissions()

    def release(self, request, pk=None):
        """POST /reservations/{id}/release/ — favqulodda qo'lda bo'shatish."""
        from rest_framework.exceptions import ValidationError

        from apps.core.models import ActivityLog

        reservation = self.get_object()
        if reservation.status != StockReservation.Status.ACTIVE:
            raise ValidationError({'detail': 'Faqat faol bron bo\'shatiladi.'})
        note = (request.data.get('note') or '').strip()
        if not note:
            raise ValidationError({'note': 'Sabab majburiy — "mol qayerga ketdi" auditda qolsin.'})

        reservation.status = StockReservation.Status.RELEASED
        reservation.released_by = request.user
        reservation.release_note = note
        reservation.save()
        self.log_action(
            ActivityLog.Action.UPDATE, reservation,
            f"Bron qo'lda bo'shatildi ({reservation.owner_number}): {note}",
        )
        return Response(self.get_serializer(reservation).data)
