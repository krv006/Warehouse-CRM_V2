"""inventory marshrutlari: ombor bo'limi."""

from django.urls import path

from apps.core.routing import DETAIL, LIST
from apps.inventory.views import (
    CategoryViewSet,
    WarehouseViewSet,
    ProductViewSet,
    ProductSpecViewSet,
    StockViewSet,
    StockMovementViewSet,
)

urlpatterns = [
    path('categories/', CategoryViewSet.as_view(LIST), name='category-list'),
    path('categories/<int:pk>/', CategoryViewSet.as_view(DETAIL), name='category-detail'),

    path('warehouses/', WarehouseViewSet.as_view(LIST), name='warehouse-list'),
    path('warehouses/<int:pk>/', WarehouseViewSet.as_view(DETAIL), name='warehouse-detail'),

    path('products/', ProductViewSet.as_view(LIST), name='product-list'),
    path('products/<int:pk>/', ProductViewSet.as_view(DETAIL), name='product-detail'),

    path('product-specs/', ProductSpecViewSet.as_view(LIST), name='productspec-list'),
    path('product-specs/<int:pk>/', ProductSpecViewSet.as_view(DETAIL), name='productspec-detail'),

    path('stocks/', StockViewSet.as_view(LIST), name='stock-list'),
    path('stocks/<int:pk>/', StockViewSet.as_view(DETAIL), name='stock-detail'),

    path('movements/', StockMovementViewSet.as_view(LIST), name='stockmovement-list'),
    path('movements/<int:pk>/', StockMovementViewSet.as_view(DETAIL), name='stockmovement-detail'),
]
