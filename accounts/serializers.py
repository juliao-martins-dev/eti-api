from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import User


class UserSerializer(serializers.ModelSerializer):
    """The profile the app shows in its header after login."""

    role_display = serializers.CharField(source='get_role_display', read_only=True)
    nivel_edukasaun_display = serializers.CharField(
        source='get_nivel_edukasaun_display', read_only=True
    )

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
            'nivel_edukasaun',
            'nivel_edukasaun_display',
            'area_estudu',
            'disiplina_hanorin',
        ]
        read_only_fields = fields


class ProfesorRosterSerializer(serializers.ModelSerializer):
    """
    One row of the dashboard's teacher roster (plan R1). Includes the fields
    the roster table shows on top of the auth profile: sexu, nu_kontaktu and
    the is_active flag behind the "Dezativadu" badge.
    """

    role_display = serializers.CharField(source='get_role_display', read_only=True)
    nivel_edukasaun_display = serializers.CharField(
        source='get_nivel_edukasaun_display', read_only=True
    )

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
            # HABILITASAUN LITERÁRIA on the printed roster is a heading over
            # these two columns, not a column of its own -- so the pair is what
            # the dashboard shows.
            'nivel_edukasaun',
            'nivel_edukasaun_display',
            'area_estudu',
            'disiplina_hanorin',
        ]
        read_only_fields = fields


class ProfesorKriaSerializer(serializers.ModelSerializer):
    """Payload of the "Aumenta Profesór" modal (plan R3)."""

    class Meta:
        model = User
        fields = [
            'numeru_id', 'naran_kompletu', 'email', 'kargu', 'nu_kontaktu', 'sexu',
            'nivel_edukasaun', 'area_estudu', 'disiplina_hanorin',
        ]


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
            'nivel_edukasaun',
            'area_estudu',
            'disiplina_hanorin',
        ]


class ProfesorResetPasswordSerializer(serializers.Serializer):
    """
    POST /api/profesor/{id}/reset-password/ -- the admin types the new password
    twice. Both copies travel and the server compares them, so a mismatched
    form cannot slip through a client that forgot to check.
    """

    password_foun = serializers.CharField(write_only=True, trim_whitespace=False)
    password_konfirma = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        if attrs['password_foun'] != attrs['password_konfirma']:
            raise serializers.ValidationError(
                {'detail': 'Password rua la hanesan.', 'code': 'password_la_hanesan'}
            )
        return attrs


class TrokaPasswordSerializer(serializers.Serializer):
    """
    POST /api/auth/troka-password/ -- the signed-in account changes its own
    password.

    Unlike the admin reset, this one demands the **old** password: the caller
    is changing their own credentials, and an unlocked laptop must not be
    enough to lock the real owner out.
    """

    password_tuan = serializers.CharField(write_only=True, trim_whitespace=False)
    password_foun = serializers.CharField(write_only=True, trim_whitespace=False)
    password_konfirma = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        if attrs['password_foun'] != attrs['password_konfirma']:
            raise serializers.ValidationError(
                {'detail': 'Password foun rua la hanesan.',
                 'code': 'password_la_hanesan'}
            )
        if attrs['password_foun'] == attrs['password_tuan']:
            raise serializers.ValidationError(
                {'detail': "Password foun tenke la hanesan ho password tuan.",
                 'code': 'password_hanesan_tuan'}
            )
        return attrs


class ProfesorHasaiSerializer(serializers.Serializer):
    """
    DELETE /api/profesor/{id}/ -- the caller re-types their own password.

    The dashboard asks for it twice, but only one copy travels: the second
    field is friction for the person at the keyboard, this is the check that
    actually holds, because anything can call the endpoint directly.
    """

    password = serializers.CharField(
        write_only=True,
        style={'input_type': 'password'},
        trim_whitespace=False,
    )


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
