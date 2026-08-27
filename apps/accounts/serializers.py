from rest_framework.serializers import CharField, ModelSerializer, ReadOnlyField

from apps.accounts.models import User


class UserSerializer(ModelSerializer):
    role_display = ReadOnlyField(source='get_role_display')

    class Meta:
        model = User
        fields = [
            'id', 'username', 'first_name', 'last_name', 'email',
            'phone', 'role', 'role_display', 'language', 'is_active', 'date_joined',
        ]
        read_only_fields = ['date_joined']


class UserCreateSerializer(ModelSerializer):
    password = CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'first_name', 'last_name', 'email',
            'phone', 'role', 'language', 'password',
        ]

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user
