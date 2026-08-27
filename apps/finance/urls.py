"""finance marshrutlari: kassa, qarz va xarajat so'rovlari."""

from django.urls import path

from apps.core.routing import DETAIL, LIST
from apps.finance.views import (
    CashCategoryViewSet,
    CashTransactionViewSet,
    ExpenseRequestViewSet,
    LoanViewSet,
)

urlpatterns = [
    path('cash-categories/', CashCategoryViewSet.as_view(LIST), name='cashcategory-list'),
    path('cash-categories/<int:pk>/', CashCategoryViewSet.as_view(DETAIL), name='cashcategory-detail'),

    path('cash-transactions/', CashTransactionViewSet.as_view(LIST), name='cashtransaction-list'),
    path('cash-transactions/summary/', CashTransactionViewSet.as_view({
        'get': 'summary',
    }), name='cashtransaction-summary'),
    path('cash-transactions/<int:pk>/', CashTransactionViewSet.as_view(DETAIL), name='cashtransaction-detail'),

    path('loans/', LoanViewSet.as_view(LIST), name='loan-list'),
    path('loans/<int:pk>/', LoanViewSet.as_view(DETAIL), name='loan-detail'),
    path('loans/<int:pk>/repay/', LoanViewSet.as_view({
        'post': 'repay',
    }), name='loan-repay'),

    path('expense-requests/', ExpenseRequestViewSet.as_view(LIST), name='expenserequest-list'),
    path('expense-requests/<int:pk>/', ExpenseRequestViewSet.as_view(DETAIL), name='expenserequest-detail'),
    path('expense-requests/<int:pk>/approve/', ExpenseRequestViewSet.as_view({
        'post': 'approve',
    }), name='expenserequest-approve'),
    path('expense-requests/<int:pk>/reject/', ExpenseRequestViewSet.as_view({
        'post': 'reject',
    }), name='expenserequest-reject'),
]
