from django.http import HttpResponse
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST

from apps.accounts.permissions import IsAdminOrReadOnly
from apps.configurator.models import Act, Configuration, ConfigurationItem
from apps.configurator.serializers import (
    ActSerializer,
    ConfigurationSerializer,
    ConfigurationItemSerializer,
)
from apps.configurator.services import build_configuration_workbook, resolve_variant
from apps.core.mixins import BaseModelViewSet
from apps.core.models import ActivityLog

XLSX_CONTENT_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


class ActViewSet(BaseModelViewSet):
    """ACT hujjatlari — faqat admin kiritadi."""

    queryset = Act.objects.select_related('created_by').all()
    serializer_class = ActSerializer
    permission_classes = [IsAdminOrReadOnly]
    search_fields = ['number', 'title']
    filterset_fields = ['is_active']


class ConfigurationViewSet(BaseModelViewSet):
    """Configurator barcha rollarga ochiq (TZ: umumiy tushunchalar)."""

    queryset = (
        Configuration.objects
        .select_related('client', 'base_product', 'act', 'warehouse', 'created_by')
        .prefetch_related('items__component__stocks')
        .all()
    )
    serializer_class = ConfigurationSerializer
    search_fields = ['number', 'client__full_name', 'client__company_name']
    filterset_fields = ['status', 'client', 'base_product', 'act']
    ordering_fields = ['created_at', 'number']

    def stock_check(self, request, pk=None):
        """GET /configurations/{id}/stock-check/ — qaysi butlovchi omborda bor."""
        configuration = self.get_object()
        variant = configuration.variant or configuration.matching_variant
        return Response({
            'configuration': configuration.number,
            'ready_variant': variant.sku if variant else None,
            'variant_price': variant.stock_price if variant else None,
            'total_price': configuration.total_price,
            'items': [
                {
                    'component': item.component.name,
                    'quantity': item.quantity,
                    'available': item.available,
                    'shortage': item.shortage,
                    'source': item.source,
                    'unit_price': item.unit_price,
                    'needs_price': item.needs_price,
                }
                for item in configuration.items.select_related('component')
            ],
        })

    def finalize(self, request, pk=None):
        """POST /configurations/{id}/finalize/ — ACT bilan yakunlash."""
        configuration = self.get_object()
        if configuration.status != Configuration.Status.DRAFT:
            return Response(
                {'detail': 'Faqat chernovik holatidagi konfiguratsiya yakunlanadi.'},
                status=HTTP_400_BAD_REQUEST,
            )
        if not configuration.act:
            return Response(
                {'detail': 'Yakunlash uchun ACT biriktirilishi shart.'},
                status=HTTP_400_BAD_REQUEST,
            )
        if not configuration.items.exists():
            return Response(
                {'detail': 'Konfiguratsiya qatorlari kiritilmagan.'},
                status=HTTP_400_BAD_REQUEST,
            )

        # TZ 6.2: narxi aniqlanmagan butlovchi bo'lsa, jarayon yakunlanmaydi
        no_price = configuration.items_without_price
        if no_price:
            return Response(
                {
                    'detail': 'Narxi kiritilmagan butlovchilar bor.',
                    'items': [item.component.name for item in no_price],
                },
                status=HTTP_400_BAD_REQUEST,
            )

        variant, created = resolve_variant(configuration)
        configuration.variant = variant
        configuration.status = Configuration.Status.READY
        configuration.save()
        self.log_action(
            ActivityLog.Action.UPDATE, configuration,
            f'Yakunlandi, variant: {variant.sku} ' + ('(yangi)' if created else '(ombordan)'),
        )
        return Response(self.get_serializer(configuration).data)

    def attach(self, request, pk=None):
        """POST /configurations/{id}/attach/ — kirim buyurtmasiga biriktirish."""
        from apps.purchases.models import Purchase

        configuration = self.get_object()
        if configuration.status != Configuration.Status.READY:
            return Response(
                {'detail': 'Avval konfiguratsiyani yakunlang.'},
                status=HTTP_400_BAD_REQUEST,
            )
        purchase = Purchase.objects.filter(pk=request.data.get('purchase')).first()
        if not purchase:
            return Response(
                {'purchase': 'Kirim buyurtmasi topilmadi.'},
                status=HTTP_400_BAD_REQUEST,
            )
        configuration.purchase = purchase
        configuration.status = Configuration.Status.ATTACHED
        configuration.save()
        self.log_action(
            ActivityLog.Action.UPDATE, configuration,
            f'Konfiguratsiya {purchase.number} buyurtmasiga biriktirildi',
        )
        return Response(self.get_serializer(configuration).data)

    def export_excel(self, request, pk=None):
        """GET /configurations/{id}/export-excel/ — chernovik Excel."""
        configuration = self.get_object()
        workbook = build_configuration_workbook(configuration)
        response = HttpResponse(content_type=XLSX_CONTENT_TYPE)
        response['Content-Disposition'] = f'attachment; filename="{configuration.number}.xlsx"'
        workbook.save(response)
        return response


class ConfigurationItemViewSet(BaseModelViewSet):
    queryset = ConfigurationItem.objects.select_related('configuration', 'component').all()
    serializer_class = ConfigurationItemSerializer
    filterset_fields = ['configuration', 'component']
