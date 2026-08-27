from rest_framework.serializers import ModelSerializer, ReadOnlyField

from apps.core.models import ActivityLog, Notification


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
