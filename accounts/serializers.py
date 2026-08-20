from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import FOTO_DEFAULT, User, bele_hasai_foto



def url_foto(user, context):
    """
    Absolute URL of a profile photo, falling back to the shared placeholder.

    An account can reach the clients with an empty `foto`: the model default is
    applied by Python, never by PostgreSQL, so anyone inserted by raw SQL -- or
    created before migration 0006 added the default -- has `''` in the column.
    Those used to serialize as `null`, which left every client to invent its
    own idea of "no photo". Falling back here means an account without a photo
    looks the same in the mobile app, the dashboard and the reports.
    """
    naran = user.foto.name or FOTO_DEFAULT
    url = user.foto.storage.url(naran)
    pedidu = context.get('request')
    return pedidu.build_absolute_uri(url) if pedidu else url


class UserSerializer(serializers.ModelSerializer):
    """
    The profile the app shows in its header after login, and the base every
    other read view of an account extends -- see `ProfesorRosterSerializer`.

    What is *not* here is as deliberate as what is: `is_active` and
    `nu_kontaktu` belong to the roster an admin reads, not to the profile a
    teacher reads about themselves.
    """

    role_display = serializers.CharField(source='get_role_display', read_only=True)
    nivel_edukasaun_display = serializers.CharField(
        source='get_nivel_edukasaun_display', read_only=True
    )
    #: Never null -- an account with no photo of its own gets the placeholder.
    foto = serializers.SerializerMethodField()

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

    def get_foto(self, obj):
        return url_foto(obj, self.context)


class ProfesorRosterSerializer(UserSerializer):
    """
    One row of the dashboard's teacher roster (plan R1).

    The roster is the auth profile plus the three columns only an admin sees:
    `sexu`, `nu_kontaktu`, and the `is_active` flag behind the "Dezativadu"
    badge. Extending `UserSerializer` says that in the code instead of
    restating twelve field names that then have to be kept in step by hand.

    (HABILITASAUN LITERÁRIA on the printed roster is a heading over
    `nivel_edukasaun` + `area_estudu`, not a column of its own, so the pair is
    what the dashboard shows -- both are inherited.)
    """

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + [
            'sexu',
            'nu_kontaktu',
            'is_active',
        ]
        read_only_fields = fields


class ProfesorKriaSerializer(serializers.ModelSerializer):
    """
    Payload of the "Aumenta Profesór" modal (plan R3), and the allowlist of
    what an admin may write about a teacher at all -- `role`, `password` and
    `is_staff` are absent on purpose, so no client can grant itself anything.
    """

    class Meta:
        model = User
        fields = [
            'numeru_id', 'naran_kompletu', 'email', 'kargu', 'nu_kontaktu', 'sexu',
            'nivel_edukasaun', 'area_estudu', 'disiplina_hanorin',
        ]


class ProfesorAtualizaSerializer(ProfesorKriaSerializer):
    """
    PATCH payload -- any subset of R3, plus the soft is_active toggle (R4).

    Editing a teacher is creating one plus the ability to deactivate, so this
    extends the create allowlist rather than restating it: a field added to
    the modal becomes editable in the same commit, and the two lists cannot
    drift apart.
    """

    class Meta(ProfesorKriaSerializer.Meta):
        fields = ProfesorKriaSerializer.Meta.fields + ['is_active']


class PasswordFounSerializer(serializers.Serializer):
    """
    The "type the new password twice" pair, shared by the admin reset and the
    self-service change.

    Both copies travel and the server compares them, so a mismatched form
    cannot slip through a client that forgot to check.

    Subclasses that add rules of their own must call `super().validate(attrs)`
    first -- the two passwords matching is the precondition for every other
    question worth asking about them.
    """

    #: Wording of the mismatch, overridden where "the new one" needs saying.
    #: Only the `code` reaches a client: both views answer with their own
    #: `detail` (see `ProfesorViewSet.reset_password`, `TrokaPasswordView`).
    ERRU_LA_HANESAN = 'Password rua la hanesan.'

    password_foun = serializers.CharField(write_only=True, trim_whitespace=False)
    password_konfirma = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        if attrs['password_foun'] != attrs['password_konfirma']:
            raise serializers.ValidationError(
                {'detail': self.ERRU_LA_HANESAN, 'code': 'password_la_hanesan'}
            )
        return attrs


class ProfesorResetPasswordSerializer(PasswordFounSerializer):
    """
    POST /api/profesor/{id}/reset-password/ -- the admin types the new password
    twice for a teacher who lost theirs.

    The old password is deliberately *not* asked for: an admin resetting an
    account cannot possibly know it. That is the whole difference from
    `TrokaPasswordSerializer`, and the reason the two stay separate.
    """


class TrokaPasswordSerializer(PasswordFounSerializer):
    """
    POST /api/auth/troka-password/ -- the signed-in account changes its own
    password.

    Unlike the admin reset, this one demands the **old** password: the caller
    is changing their own credentials, and an unlocked laptop must not be
    enough to lock the real owner out.
    """

    ERRU_LA_HANESAN = 'Password foun rua la hanesan.'

    password_tuan = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        attrs = super().validate(attrs)
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
        # behind in MEDIA_ROOT forever. `bele_hasai_foto` spares the shared
        # placeholder: a teacher uploading their first photo is replacing
        # FOTO_DEFAULT, and that file belongs to every other account that has
        # not uploaded one yet.
        if tuan != instance.foto.name and bele_hasai_foto(tuan):
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
