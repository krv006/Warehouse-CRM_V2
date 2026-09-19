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


class RoadmapView(APIView):
    """GET …/roadmap/ — zanjir ko'zgusi (YANGI-OQIM B8).

    Uch kirish nuqtasi (ZVK/CFG/SHT) bir xil javob qaytaradi. Hujjat
    ko'rinish qoidalariga BO'YSUNMAYDI — zanjirdagi beshta rol ham to'liq
    ko'radi (aks holda bugalter ZVK roadmapida 404 olardi, §3.13); evaziga
    javobda pulga oid hech narsa yo'q. Qadam ichiga kirishni `can_open`
    aytadi — front ruxsat matritsasini takrorlamaydi.
    """

    kind = None  # 'request' | 'configuration' | 'contract'

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, pk):
        from django.shortcuts import get_object_or_404

        from apps.configurator.models import Configuration, ConfigurationRequest
        from apps.core.roadmap import build_roadmap

        model = {
            'request': ConfigurationRequest,
            'configuration': Configuration,
            'contract': Contract,
        }[self.kind]
        document = get_object_or_404(model, pk=pk)
        return Response(build_roadmap(document, request.user))


class RoadmapListView(APIView):
    """GET /roadmaps/ — bosh sahifa uchun zanjirlar ro'yxati (7-to'plam §1).

    Joriy foydalanuvchi QATNASHAYOTGAN zanjirlar: egasi bo'lgan yoki joriy
    qadami uning roliga tegishli (bugalter/buyurtmachi uchun asosiy shart —
    ular hujjat egasi emas, lekin navbat ularga keladi); admin — hammasi.
    Har bir element detal `roadmap` javobi bilan BIR XIL shaklda — front
    bitta komponentni o'zgarishsiz ishlatadi. Tartib: muddatdan o'tgan →
    navbati shu foydalanuvchida → kutish vaqti bo'yicha.
    """

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        from apps.core.roadmap import build_roadmap_list

        state = request.query_params.get('state', 'open')
        if state not in ('open', 'closed', 'all'):
            state = 'open'
        try:
            limit = int(request.query_params.get('limit', 10))
        except (TypeError, ValueError):
            limit = 10
        limit = max(1, min(limit, 50))

        rows = build_roadmap_list(request.user, state=state)
        return Response({'count': len(rows), 'results': rows[:limit]})


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


class MyWorkView(APIView):
    """GET /my-work/ — "menga taqalgan ish" navbati (EGALIK §2.1).

    Javob: {counts, items}. Havola va matnni backend qurmaydi — `entity`+`id`
    va `reason` kodi qaytadi, front o'zi manzil va ko'rsatma matnini chizadi.
    """

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        from apps.core.services import collect_work

        return Response(collect_work(request.user, include_items=True))


class SidebarCountsView(APIView):
    """GET /sidebar-counts/ — yon panel hisoblagichi (EGALIK §2.4).

    `my-work` bilan bitta `collect_work()` dan chiqadi — raqamlar ta'rifan
    mos. Faqat COUNT so'rovlari yuradi (har 60 soniyada chaqiriladi).
    """

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        from apps.core.services import collect_work

        return Response(collect_work(request.user, include_items=False)['counts'])


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
    # 4-to'plam §4: object_id — "shu hujjat bo'yicha xabarlar" ko'rinishi uchun
    filterset_fields = ['is_read', 'level', 'entity', 'object_id']

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

    def mark_all_read(self, request):
        """POST /notifications/mark-all-read/ — hammasini bittada (4-to'plam §4).

        Queryset o'z eslatmalari bilan cheklangan — birovnikiga tegilmaydi;
        bitta UPDATE, sikl yo'q.
        """
        updated = self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({'updated': updated})
