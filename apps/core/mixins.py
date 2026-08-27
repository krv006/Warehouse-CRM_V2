from rest_framework.viewsets import ModelViewSet

from apps.core.models import ActivityLog


class ActivityLogMixin:
    """Har bir yozuv amali uchun audit log qoldiradi."""

    def _current_user(self):
        user = getattr(self.request, 'user', None)
        return user if user and user.is_authenticated else None

    def log_action(self, action, instance, description=''):
        ActivityLog.objects.create(
            user=self._current_user(),
            action=action,
            entity=instance.__class__.__name__,
            object_id=str(instance.pk),
            description=description or str(instance),
        )

    def _save_kwargs(self, serializer):
        model = serializer.Meta.model
        field_names = {field.name for field in model._meta.fields}
        if 'created_by' in field_names:
            return {'created_by': self._current_user()}
        return {}

    def perform_create(self, serializer):
        instance = serializer.save(**self._save_kwargs(serializer))
        self.log_action(ActivityLog.Action.CREATE, instance)

    def perform_update(self, serializer):
        instance = serializer.save()
        self.log_action(ActivityLog.Action.UPDATE, instance)

    def perform_destroy(self, instance):
        self.log_action(ActivityLog.Action.DELETE, instance)
        instance.delete()


class BaseModelViewSet(ActivityLogMixin, ModelViewSet):
    """Loyihadagi barcha ViewSet'lar uchun asos."""
