from django.contrib.admin import ModelAdmin, register

from apps.core.models import ActivityLog, CompanyProfile, Notification


@register(CompanyProfile)
class CompanyProfileAdmin(ModelAdmin):
    list_display = ['name', 'inn', 'phone', 'email', 'updated_at']

    def has_add_permission(self, request):
        return not CompanyProfile.objects.exists()


@register(ActivityLog)
class ActivityLogAdmin(ModelAdmin):
    list_display = ['created_at', 'user', 'action', 'entity', 'object_id']
    list_filter = ['action', 'entity']
    search_fields = ['entity', 'description']


@register(Notification)
class NotificationAdmin(ModelAdmin):
    list_display = ['title', 'level', 'due_date', 'is_read', 'created_at']
    list_filter = ['level', 'is_read']
