from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncMonth
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.accounts.permissions import IsAdmin
from apps.clients.models import Client
from apps.core.choices import Direction
from apps.core.mixins import BaseModelViewSet
from apps.core.models import ActivityLog, CompanyProfile, Notification
from apps.core.serializers import (
    ActivityLogSerializer,
    CompanyProfileSerializer,
    NotificationSerializer,
)
from apps.finance.models import CashTransaction
from apps.inventory.models import Product
from apps.purchases.models import Purchase
from apps.sales.models import Contract, Lead


class DashboardView(APIView):
    """Umumiy hisobot: kassa, kirim, chiqim, sotuv va muddatlar.

    `kassa` bloki (qoldiq, kirim/chiqim yig'indilari, yacheykalar) faqat
    admin va bugalterga beriladi — TZ 8.2 bo'yicha kassa boshqa rollarga
    yopiq, front yashirgani bilan API dan sizib chiqmasligi kerak.
    """

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        income = CashTransaction.objects.filter(direction=Direction.IN)
        expense = CashTransaction.objects.filter(direction=Direction.OUT)
        income_total = income.aggregate(t=Sum('amount'))['t'] or 0
        expense_total = expense.aggregate(t=Sum('amount'))['t'] or 0
        can_see_cash = request.user.is_admin or request.user.is_bugalter

        active_contracts = (
            Contract.objects
            .filter(status=Contract.Status.ACTIVE)
            .select_related('client')
        )
        deadlines = sorted(
            (
                {
                    'id': contract.id,
                    'number': contract.number,
                    'client': contract.client.display_name,
                    'days_left': contract.days_left,
                    'color': contract.color,
                    'balance': contract.balance,
                }
                for contract in active_contracts
            ),
            key=lambda row: (row['days_left'] is None, row['days_left']),
        )

        low_stock = [
            {
                'id': product.id,
                'name': product.name,
                'sku': product.sku,
                'total_stock': product.total_stock,
                'reorder_level': product.reorder_level,
            }
            for product in Product.objects.filter(is_active=True).prefetch_related('stocks')
            if product.is_low_stock
        ]

        return Response({
            'kassa': {
                'income_total': income_total,
                'expense_total': expense_total,
                'balance': income_total - expense_total,
                'income_by_category': list(
                    income.values('category__code', 'category__name')
                    .annotate(total=Sum('amount')).order_by('-total')
                ),
                'expense_by_category': list(
                    expense.values('category__code', 'category__name')
                    .annotate(total=Sum('amount')).order_by('-total')
                ),
            } if can_see_cash else None,
            'kirim': {
                'by_type': list(
                    Purchase.objects.values('type').annotate(count=Count('id')).order_by()
                ),
                'in_transit': Purchase.objects.filter(
                    status__in=[Purchase.Status.ORDERED, Purchase.Status.IN_TRANSIT],
                ).count(),
            },
            'sales': {
                'contracts_by_status': list(
                    Contract.objects.values('status').annotate(count=Count('id')).order_by()
                ),
                'leads_by_stage': list(
                    Lead.objects.values('stage').annotate(count=Count('id')).order_by()
                ),
                'monthly_income': list(
                    income
                    .annotate(month=TruncMonth('occurred_at'))
                    .values('month')
                    .annotate(total=Sum('amount'))
                    .order_by('month')
                ),
            },
            'clients': {
                'total': Client.objects.count(),
                'individual': Client.objects.filter(type=Client.Type.INDIVIDUAL).count(),
                'legal': Client.objects.filter(type=Client.Type.LEGAL).count(),
            },
            'ombor': {
                'product_count': Product.objects.filter(is_active=True).count(),
                'low_stock': low_stock,
            },
            'deadlines': deadlines,
            'notifications': NotificationSerializer(
                Notification.objects.filter(user=request.user, is_read=False)[:10],
                many=True,
            ).data,
        })


class CompanyProfileViewSet(BaseModelViewSet):
    """Bajaruvchi (o'z firmamiz) rekvizitlari — yagona yozuv.

    GET — hamma autentifikatsiyalangan foydalanuvchi o'qiydi (shartnoma chop
    etishda kerak), PUT/PATCH — faqat admin to'ldiradi va tahrirlaydi.
    """

    queryset = CompanyProfile.objects.all()
    serializer_class = CompanyProfileSerializer

    def get_permissions(self):
        if self.action in ('update', 'partial_update'):
            return [IsAdmin()]
        return super().get_permissions()

    def get_object(self):
        return CompanyProfile.load()


class ActivityLogViewSet(ReadOnlyModelViewSet):
    """Kim nima qilgani — faqat admin ko'radi."""

    queryset = ActivityLog.objects.select_related('user').all()
    serializer_class = ActivityLogSerializer
    permission_classes = [IsAdmin]
    search_fields = ['entity', 'description']
    filterset_fields = ['user', 'action', 'entity']


class NotificationViewSet(ReadOnlyModelViewSet):
    """Foydalanuvchining eslatmalari."""

    serializer_class = NotificationSerializer
    filterset_fields = ['is_read', 'level', 'entity']

    def get_queryset(self):
        # §4.4: faqat o'ziniki — user=None "e'lon taxtasi" endi mavjud emas
        if getattr(self, 'swagger_fake_view', False) or not self.request.user.is_authenticated:
            return Notification.objects.none()
        return Notification.objects.filter(user=self.request.user)

    def mark_read(self, request, pk=None):
        """POST /notifications/{id}/mark-read/ — o'qilgan deb belgilash."""
        notification = self.get_object()
        notification.is_read = True
        notification.save()
        return Response(self.get_serializer(notification).data)
