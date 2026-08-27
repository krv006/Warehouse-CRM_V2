from django.contrib.admin import ModelAdmin, register

from apps.core.models import ActivityLog, Notification


@register(ActivityLog)
class ActivityLogAdmin(ModelAdmin):
    list_display = ['created_at', 'user', 'action', 'entity', 'object_id']
    list_filter = ['action', 'entity']
    search_fields = ['entity', 'description']


@register(Notification)
class NotificationAdmin(ModelAdmin):
    list_display = ['title', 'level', 'due_date', 'is_read', 'created_at']
    list_filter = ['level', 'is_read']
