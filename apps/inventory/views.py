from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.inventory.models import (
    Warehouse,
    Product,
    ProductSpec,
    Stock,
    StockMovement,
)
from apps.inventory.serializers import (
    WarehouseSerializer,
    ProductSerializer,
    ProductSpecSerializer,
    StockSerializer,
    StockMovementSerializer,
)


class WarehouseViewSet(ReadOnlyModelViewSet):
    """Omborlar — ma'lumotnoma, faqat o'qish uchun."""

    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer
    search_fields = ['name', 'address']
    filterset_fields = ['is_active']


class ProductViewSet(ReadOnlyModelViewSet):
    """Mahsulotlar katalogi — faqat o'qish.

    Yangi mahsulot alohida "qo'shish" oynasi orqali emas, Buyurtmachi
    to'ldirish buyurtmasiga qator qo'shganda katalogga tushadi (TZ 7).
    """

    queryset = (
        Product.objects
        .prefetch_related('stocks', 'specs__component')
        .all()
    )
    serializer_class = ProductSerializer
    search_fields = ['name', 'sku']
    filterset_fields = ['is_active', 'kind', 'base_model']
    ordering_fields = ['name', 'sale_price', 'created_at']


class ProductSpecViewSet(ReadOnlyModelViewSet):
    """Bazaviy model tarkibi — o'zgarishi ACT asosida configurator orqali (TZ 6.3)."""

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
