from rest_framework.serializers import ModelSerializer, ReadOnlyField, ValidationError

from apps.clients.models import Client

REQUIRED_BY_TYPE = {
    Client.Type.INDIVIDUAL: {
        'full_name': 'Jismoniy shaxs uchun F.I.SH majburiy.',
        'passport': 'Jismoniy shaxs uchun passport majburiy.',
        'jshshir': 'Jismoniy shaxs uchun JSHSHIR majburiy.',
    },
    Client.Type.LEGAL: {
        'company_name': 'Yuridik shaxs uchun kompaniya nomi majburiy.',
        'inn': 'Yuridik shaxs uchun INN majburiy.',
        'jshshir': 'Yuridik shaxs uchun JSHSHIR majburiy.',
        'director_name': 'Yuridik shaxs uchun rahbar F.I.SH majburiy.',
        'address': 'Yuridik shaxs uchun manzil majburiy.',
    },
}


class ClientSerializer(ModelSerializer):
    type_display = ReadOnlyField(source='get_type_display')
    display_name = ReadOnlyField()

    class Meta:
        model = Client
        fields = [
            'id', 'type', 'type_display', 'display_name', 'full_name', 'passport',
            'company_name', 'inn', 'director_name', 'jshshir', 'phone', 'email',
            'address', 'note', 'created_by', 'created_at',
        ]
        read_only_fields = ['created_by']

    def validate(self, attrs):
        instance = self.instance
        client_type = attrs.get('type') or (instance.type if instance else Client.Type.INDIVIDUAL)
        errors = {}
        for field, message in REQUIRED_BY_TYPE[client_type].items():
            value = attrs.get(field, getattr(instance, field, None) if instance else None)
            if not value:
                errors[field] = message
        if errors:
            raise ValidationError(errors)
        return attrs
