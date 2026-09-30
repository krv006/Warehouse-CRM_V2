from rest_framework.serializers import ModelSerializer, ReadOnlyField

from apps.core.models import ActivityLog, CompanyProfile, Notification


class CompanyProfileSerializer(ModelSerializer):
    """Bajaruvchi rekvizitlari — hamma o'qiydi, admin tahrirlaydi."""

    class Meta:
        model = CompanyProfile
        fields = [
            'id', 'name', 'inn', 'phone', 'email', 'address', 'city',
            'bank_name', 'mfo', 'account_number', 'director_name', 'director_title',
            'oked', 'registration_code', 'license',
            'contract_terms', 'admin_approval_threshold',
            'replenishment_approval_threshold',
            'sla_cutoff_hour', 'sla_working_days',
            'contract_reservation_days', 'configuration_reservation_days',
            'vat_recoverable', 'default_customs_fee',
            # 28-§8/27-§3: `markup_percent` (narxni YASAYDI) shu paytgacha bu
            # serializerda umuman yo'q edi — admin uni hech qachon qo'ya
            # olmagan (frontend forma bo'lsa ham PATCH jimgina tashlab
            # ketardi). `min_margin_percent` (narxni TEKSHIRADI, 27-§3) —
            # ikkalasi bir vaqtda sozlanishi kerak (27-§5 case 16).
            'markup_percent', 'min_margin_percent',
            'updated_at',
        ]
        read_only_fields = ['id', 'updated_at']


class ActivityLogSerializer(ModelSerializer):
    user_name = ReadOnlyField(source='user.username')
    action_display = ReadOnlyField(source='get_action_display')

    class Meta:
        model = ActivityLog
        fields = [
            'id', 'user', 'user_name', 'action', 'action_display',
            'entity', 'object_id', 'description', 'created_at',
        ]
        read_only_fields = fields


class NotificationSerializer(ModelSerializer):
    level_display = ReadOnlyField(source='get_level_display')

    class Meta:
        model = Notification
        fields = [
            'id', 'user', 'title', 'message', 'level', 'level_display',
            'entity', 'object_id', 'due_date', 'is_read', 'created_at',
        ]
        read_only_fields = ['user', 'title', 'message', 'level', 'entity', 'object_id', 'due_date']
