from rest_framework.serializers import (
    ModelSerializer,
    ReadOnlyField,
    SerializerMethodField,
)

from apps.configurator.models import Act, Configuration, ConfigurationItem


class ActSerializer(ModelSerializer):
    class Meta:
        model = Act
        fields = [
            'id', 'number', 'title', 'description', 'issued_at',
            'file', 'is_active', 'created_by', 'created_at',
        ]
        read_only_fields = ['created_by']


class ConfigurationItemSerializer(ModelSerializer):
    component_name = ReadOnlyField(source='component.name')
    subtotal = ReadOnlyField()
    available = ReadOnlyField()
    shortage = ReadOnlyField()
    source = ReadOnlyField()

    class Meta:
        model = ConfigurationItem
        fields = [
            'id', 'component', 'component_name', 'label', 'quantity',
            'unit_price', 'subtotal', 'available', 'shortage', 'source',
        ]


class ConfigurationSerializer(ModelSerializer):
    items = ConfigurationItemSerializer(many=True)
    client_name = ReadOnlyField(source='client.display_name')
    base_product_name = ReadOnlyField(source='base_product.name')
    status_display = ReadOnlyField(source='get_status_display')
    act_number = ReadOnlyField(source='act.number')
    total_price = ReadOnlyField()
    missing_count = SerializerMethodField()

    class Meta:
        model = Configuration
        fields = [
            'id', 'number', 'client', 'client_name', 'base_product', 'base_product_name',
            'warehouse', 'act', 'act_number', 'purchase', 'status', 'status_display',
            'note', 'items', 'total_price', 'missing_count',
            'created_by', 'created_at',
        ]
        read_only_fields = ['number', 'created_by', 'purchase']

    def get_missing_count(self, obj):
        return len(obj.missing_items)

    def create(self, validated_data):
        items = validated_data.pop('items', [])
        configuration = Configuration.objects.create(**validated_data)
        for item in items:
            ConfigurationItem.objects.create(configuration=configuration, **item)
        return configuration

    def update(self, instance, validated_data):
        items = validated_data.pop('items', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if items is not None:
            instance.items.all().delete()
            for item in items:
                ConfigurationItem.objects.create(configuration=instance, **item)
        return instance
