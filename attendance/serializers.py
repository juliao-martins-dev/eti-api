from decimal import ROUND_DOWN

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from .models import ListaPrezensa, Marka, Prezensa, Sesaun, Tipu


class KoordenadaField(serializers.DecimalField):
    """
    A GPS coordinate exactly as the phone reports it.

    Android and iOS hand out a dozen or more decimals (-8.5523361234567), and
    DRF's default precision check turned that into "Ensure that there are no
    more than 6 decimal places" -- an error the teacher standing in the yard
    can do nothing about. The extra digits are noise well below the accuracy
    of any phone GPS, so we round them off to the six decimals we store
    (~0.11 m) instead of refusing the punch.

    Only the whole part is still checked, because a value like 1234.5 is a
    broken client, not a rounding problem.
    """

    def validate_precision(self, value):
        maksimu = self.max_digits - self.decimal_places
        inteiru = value.copy_abs().to_integral_value(rounding=ROUND_DOWN)
        if len(f'{inteiru:f}') > maksimu:
            self.fail('max_whole_digits', max_whole_digits=maksimu)
        # DRF quantizes to `decimal_places` right after this returns.
        return value


class MarkaSerializer(serializers.ModelSerializer):
    """One punch with the evidence collected when it was made."""

    sesaun_display = serializers.CharField(source='get_sesaun_display', read_only=True)
    tipu_display = serializers.CharField(source='get_tipu_display', read_only=True)
    kolumna = serializers.CharField(read_only=True)
    oras_orariu = serializers.TimeField(read_only=True)
    atrazadu = serializers.BooleanField(read_only=True)

    class Meta:
        model = Marka
        fields = [
            'id',
            'sesaun',
            'sesaun_display',
            'tipu',
            'tipu_display',
            'kolumna',
            'oras',
            'oras_orariu',
            'atrazadu',
            'rejistu_iha',
            'foto',
            'latitude',
            'longitude',
            'presizaun',
            'distansia_metru',
            'iha_eskola',
        ]
        read_only_fields = fields


class PrezensaSerializer(serializers.ModelSerializer):
    """One day of the book: the printed grid plus the punches behind it."""

    loron = serializers.CharField(read_only=True)
    profesor = serializers.CharField(source='lista.profesor', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    oras_dader_tama = serializers.TimeField(read_only=True)
    oras_dader_fila = serializers.TimeField(read_only=True)
    oras_lorokraik_tama = serializers.TimeField(read_only=True)
    oras_lorokraik_fila = serializers.TimeField(read_only=True)

    marka = MarkaSerializer(many=True, read_only=True)

    class Meta:
        model = Prezensa
        fields = [
            'id',
            'profesor',
            'data',
            'loron',
            'oras_dader_tama',
            'oras_dader_fila',
            'oras_lorokraik_tama',
            'oras_lorokraik_fila',
            'status',
            'status_display',
            'obs',
            'marka',
        ]
        read_only_fields = fields


class PrezensaOhinSerializer(PrezensaSerializer):
    """
    The home screen: today's row plus the state of the two buttons, so the app
    does not have to know the session cut-off itself.
    """

    sesaun = serializers.SerializerMethodField()
    oras_tama = serializers.SerializerMethodField()
    oras_fila = serializers.SerializerMethodField()
    bele_clock_in = serializers.SerializerMethodField()
    bele_clock_out = serializers.SerializerMethodField()

    class Meta(PrezensaSerializer.Meta):
        fields = PrezensaSerializer.Meta.fields + [
            'sesaun',
            'oras_tama',
            'oras_fila',
            'bele_clock_in',
            'bele_clock_out',
        ]
        read_only_fields = fields

    def _sesaun(self, obj):
        return Prezensa.sesaun_ba(timezone.localtime().time())

    def get_sesaun(self, obj):
        return self._sesaun(obj)

    def get_oras_tama(self, obj):
        return obj.oras_ba(self._sesaun(obj), Tipu.TAMA)

    def get_oras_fila(self, obj):
        return obj.oras_ba(self._sesaun(obj), Tipu.FILA)

    def get_bele_clock_in(self, obj):
        if obj.sabadu and self._sesaun(obj) == Sesaun.LOROKRAIK:
            return False
        return self.get_oras_tama(obj) is None

    def get_bele_clock_out(self, obj):
        return self.get_oras_tama(obj) is not None and self.get_oras_fila(obj) is None


class MarkaPrezensaSerializer(serializers.Serializer):
    """
    Payload of the Clock In / Clock out buttons: the photo taken at the punch
    and where the device was when it was taken.
    """

    foto = serializers.ImageField()
    latitude = KoordenadaField(
        max_digits=9, decimal_places=6, min_value=-90, max_value=90,
    )
    longitude = KoordenadaField(
        max_digits=9, decimal_places=6, min_value=-180, max_value=180,
    )
    presizaun = serializers.FloatField(required=False, allow_null=True, min_value=0)
    # Which half of the day to write to. Left out, the server decides from its
    # own clock, which is what the two buttons of the app do; sent explicitly,
    # it lets a teacher close a session the clock has already moved past.
    sesaun = serializers.ChoiceField(choices=Sesaun.choices, required=False)


class ProfesorSerializer(serializers.ModelSerializer):
    """Just enough of the teacher to identify a row in the daily report."""

    class Meta:
        model = get_user_model()
        fields = ['id', 'numeru_id', 'naran_kompletu', 'kargu', 'foto']
        read_only_fields = fields


class PrezensaProfesorSerializer(serializers.Serializer):
    """
    One line of the daily report: a teacher, and their day if they punched.
    `prezensa` is null for a teacher who has not marked anything yet, which is
    the point of the report -- absences are what the director is looking for.
    """

    profesor = ProfesorSerializer(read_only=True)
    prezensa = PrezensaSerializer(read_only=True, allow_null=True)
    marka_ona = serializers.BooleanField(read_only=True)


class PrezensaLigeruSerializer(PrezensaSerializer):
    """PrezensaSerializer without the nested punches, for `?marka=false`."""

    class Meta(PrezensaSerializer.Meta):
        fields = [f for f in PrezensaSerializer.Meta.fields if f != 'marka']
        read_only_fields = fields


class PrezensaProfesorLoronSerializer(PrezensaProfesorSerializer):
    """
    A daily-report line that also carries its calendar day, for
    /api/prezensa/hotu/ -- an empty day has `prezensa: null`, so the date
    cannot live inside it.
    """

    data = serializers.DateField(read_only=True)


class PrezensaProfesorLoronLigeruSerializer(PrezensaProfesorLoronSerializer):
    prezensa = PrezensaLigeruSerializer(read_only=True, allow_null=True)


#: Everything an administrator may hand-write onto a day. PRESENT is absent
#: on purpose: it can only come from a punch.
MANUAL_STATUS = [
    choice for choice in Prezensa.Status.choices
    if choice[0] != Prezensa.Status.PRESENT
]


class StatusRejistuSerializer(serializers.Serializer):
    """POST /api/prezensa/status/ -- a leave/mission/holiday over a range (R5)."""

    profesor = serializers.IntegerField()
    status = serializers.ChoiceField(choices=MANUAL_STATUS)
    husi = serializers.DateField()
    too = serializers.DateField()
    obs = serializers.CharField(required=False, allow_blank=True, default='')


class StatusHasaiSerializer(serializers.Serializer):
    """DELETE /api/prezensa/status/ -- return a hand-written day to "no record"."""

    profesor = serializers.IntegerField()
    data = serializers.DateField()


class ListaPrezensaSerializer(serializers.ModelSerializer):
    """A monthly sheet with its rows -- the "Historia" tab."""

    profesor = serializers.CharField(source='profesor.naran_kompletu', read_only=True)
    fulan_display = serializers.CharField(source='get_fulan_display', read_only=True)
    prezensa = PrezensaSerializer(many=True, read_only=True)

    class Meta:
        model = ListaPrezensa
        fields = [
            'id',
            'profesor',
            'kargu',
            'fulan',
            'fulan_display',
            'tinan',
            'prezensa',
        ]
        read_only_fields = fields
