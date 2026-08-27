from apps.accounts.permissions import InventoryAccess
from apps.core.mixins import BaseModelViewSet
from apps.core.models import ActivityLog
from apps.inventory.models import (
    Category,
    Warehouse,
    Product,
    ProductSpec,
    Stock,
    StockMovement,
)
from apps.inventory.serializers import (
    CategorySerializer,
    WarehouseSerializer,
    ProductSerializer,
    ProductSpecSerializer,
    StockSerializer,
    StockMovementSerializer,
)
from apps.inventory.services import sync_stock


class CategoryViewSet(BaseModelViewSet):
    queryset = Category.objects.select_related('parent').all()
    serializer_class = CategorySerializer
    permission_classes = [InventoryAccess]
    search_fields = ['name']
    filterset_fields = ['parent']


class WarehouseViewSet(BaseModelViewSet):
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer
    permission_classes = [InventoryAccess]
    search_fields = ['name', 'address']
    filterset_fields = ['is_active']


class ProductViewSet(BaseModelViewSet):
    queryset = (
        Product.objects
        .select_related('category')
        .prefetch_related('stocks', 'specs__component')
        .all()
    )
    serializer_class = ProductSerializer
    permission_classes = [InventoryAccess]
    search_fields = ['name', 'sku', 'barcode']
    filterset_fields = ['category', 'is_active', 'unit', 'kind']
    ordering_fields = ['name', 'sale_price', 'created_at']


class ProductSpecViewSet(BaseModelViewSet):
    queryset = ProductSpec.objects.select_related('product', 'component').all()
    serializer_class = ProductSpecSerializer
    permission_classes = [InventoryAccess]
    filterset_fields = ['product', 'component']


class StockViewSet(BaseModelViewSet):
    queryset = Stock.objects.select_related('product', 'warehouse').all()
    serializer_class = StockSerializer
    permission_classes = [InventoryAccess]
    filterset_fields = ['product', 'warehouse']


class StockMovementViewSet(BaseModelViewSet):
    queryset = StockMovement.objects.select_related('product', 'warehouse', 'created_by').all()
    serializer_class = StockMovementSerializer
    permission_classes = [InventoryAccess]
    filterset_fields = ['product', 'warehouse', 'type', 'reason']

    def perform_create(self, serializer):
        movement = serializer.save(created_by=self._current_user())
        sync_stock(movement)
        self.log_action(ActivityLog.Action.CREATE, movement)
