"""inventory marshrutlari: ombor ma'lumotnomasi (faqat o'qish).

TZ mahsulot va ombor mavjud deb qaraydi, ularni kim kiritishi yozilmagan —
shuning uchun katalog Django admin panelidan yuritiladi, API faqat ko'rsatadi.
Qoldiq esa faqat Kirim va Chiqim jarayonlari orqali o'zgaradi (TZ 1-bo'lim).
"""

from django.urls import path

from apps.core.routing import DETAIL, LIST, READ_DETAIL, READ_LIST
from apps.inventory.views import (
    WarehouseViewSet,
    ProductViewSet,
    ProductSpecViewSet,
    StockViewSet,
    StockMovementViewSet,
)

urlpatterns = [
    path('warehouses/', WarehouseViewSet.as_view(READ_LIST), name='warehouse-list'),
    path('warehouses/<int:pk>/', WarehouseViewSet.as_view(READ_DETAIL), name='warehouse-detail'),

    path('products/', ProductViewSet.as_view(READ_LIST), name='product-list'),
    path('products/<int:pk>/', ProductViewSet.as_view(READ_DETAIL), name='product-detail'),

    # Tarkib (ichidagi configlar): o'qish hammaga, yozish engineer (admin)
    path('product-specs/', ProductSpecViewSet.as_view(LIST), name='productspec-list'),
    path('product-specs/<int:pk>/', ProductSpecViewSet.as_view(DETAIL), name='productspec-detail'),

    path('stocks/', StockViewSet.as_view(READ_LIST), name='stock-list'),
    path('stocks/<int:pk>/', StockViewSet.as_view(READ_DETAIL), name='stock-detail'),

    path('movements/', StockMovementViewSet.as_view(READ_LIST), name='stockmovement-list'),
    path('movements/<int:pk>/', StockMovementViewSet.as_view(READ_DETAIL), name='stockmovement-detail'),
]
