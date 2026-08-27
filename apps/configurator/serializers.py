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
    stock_price = ReadOnlyField()
    needs_price = ReadOnlyField()

    class Meta:
        model = ConfigurationItem
        fields = [
            'id', 'component', 'component_name', 'label', 'quantity',
            'unit_price', 'stock_price', 'needs_price', 'subtotal',
            'available', 'shortage', 'source',
        ]


class ConfigurationSerializer(ModelSerializer):
    items = ConfigurationItemSerializer(many=True)
    client_name = ReadOnlyField(source='client.display_name')
    base_product_name = ReadOnlyField(source='base_product.name')
    status_display = ReadOnlyField(source='get_status_display')
    act_number = ReadOnlyField(source='act.number')
    total_price = ReadOnlyField()
    items_total = ReadOnlyField()
    variant_sku = ReadOnlyField(source='variant.sku')
    missing_count = SerializerMethodField()
    ready_variant = SerializerMethodField()

    class Meta:
        model = Configuration
        fields = [
            'id', 'number', 'client', 'client_name', 'base_product', 'base_product_name',
            'warehouse', 'act', 'act_number', 'purchase', 'status', 'status_display',
            'note', 'items', 'items_total', 'total_price', 'variant', 'variant_sku',
            'ready_variant', 'missing_count',
            'created_by', 'created_at',
        ]
        read_only_fields = ['number', 'created_by', 'purchase', 'variant']

    def get_missing_count(self, obj):
        return len(obj.missing_items)

    def get_ready_variant(self, obj):
        """Xuddi shu tarkib omborda tayyor pozitsiya sifatida bormi (TZ 6.2)."""
        variant = obj.variant or obj.matching_variant
        if not variant:
            return None
        return {'id': variant.id, 'sku': variant.sku, 'price': variant.stock_price}

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
