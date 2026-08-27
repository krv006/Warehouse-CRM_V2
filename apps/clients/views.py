from apps.clients.models import Client
from apps.clients.serializers import ClientSerializer
from apps.accounts.permissions import CanManageClients
from apps.core.mixins import BaseModelViewSet


class ClientViewSet(BaseModelViewSet):
    """Client qo'shish sales va adminda bor, bugalterda yo'q."""

    queryset = Client.objects.select_related('created_by').all()
    serializer_class = ClientSerializer
    permission_classes = [CanManageClients]
    search_fields = ['full_name', 'company_name', 'phone', 'inn', 'passport', 'jshshir']
    filterset_fields = ['type']
    ordering_fields = ['created_at', 'full_name', 'company_name']
