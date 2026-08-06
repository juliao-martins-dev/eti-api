from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import User


class UserSerializer(serializers.ModelSerializer):
    """The profile the app shows in its header after login."""

    role_display = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = User
        fields = [
            'id',
            'numeru_id',
            'email',
            'naran_kompletu',
            'kargu',
            'foto',
            'role',
            'role_display',
        ]
        read_only_fields = fields


class ProfesorRosterSerializer(serializers.ModelSerializer):
    """
    One row of the dashboard's teacher roster (plan R1). Includes the fields
    the roster table shows on top of the auth profile: sexu, nu_kontaktu and
    the is_active flag behind the "Dezativadu" badge.
    """

    role_display = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = User
        fields = [
            'id',
            'numeru_id',
            'email',
            'naran_kompletu',
            'kargu',
            'foto',
            'role',
            'role_display',
            'sexu',
            'nu_kontaktu',
            'is_active',
        ]
        read_only_fields = fields


class ProfesorKriaSerializer(serializers.ModelSerializer):
    """Payload of the "Aumenta Profesór" modal (plan R3)."""

    class Meta:
        model = User
        fields = ['numeru_id', 'naran_kompletu', 'email', 'kargu', 'nu_kontaktu', 'sexu']


class ProfesorAtualizaSerializer(serializers.ModelSerializer):
    """PATCH payload -- any subset of R3, plus the soft is_active toggle (R4)."""

    class Meta:
        model = User
        fields = [
            'numeru_id',
            'naran_kompletu',
            'email',
            'kargu',
            'nu_kontaktu',
            'sexu',
            'is_active',
        ]


class FotoSerializer(serializers.ModelSerializer):
    """
    The photo upload on the Perfil screen. `foto` is the only field a teacher
    may change about themselves -- name, kargu, numeru ID and role belong to
    the school, so anything else in the payload is ignored.
    """

    class Meta:
        model = User
        fields = ['foto']
        extra_kwargs = {'foto': {'required': True, 'allow_null': False}}

    def update(self, instance, validated_data):
        # Keep the *name*, not the FieldFile: FieldFile.delete() would also
        # blank the field on the instance we are about to return.
        tuan = instance.foto.name
        instance = super().update(instance, validated_data)
        # Drop the replaced file, otherwise every new photo leaves the old one
        # behind in MEDIA_ROOT forever.
        if tuan and tuan != instance.foto.name:
            instance.foto.storage.delete(tuan)
        return instance


class LoginSerializer(TokenObtainPairSerializer):
    """
    Email + password -> access / refresh pair, plus the teacher's profile so
    the app does not need a second round trip to draw its header.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['naran_kompletu'] = user.naran_kompletu
        token['role'] = user.role
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = UserSerializer(self.user, context=self.context).data
        return data


class LogoutSerializer(serializers.Serializer):
    """The refresh token to blacklist."""

    refresh = serializers.CharField()
