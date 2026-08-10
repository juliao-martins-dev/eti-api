from calendar import monthrange
from datetime import date, time

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from accounts.models import naran_foto_uniku

from .geo import distansia_husi_eskola, iha_eskola


def foto_marka(instance, filename):
    """
    Punch evidence -- `upload_to` for `Marka.foto`. Kept in the same
    year/month folders as before, with a name that is never reused so an old
    URL can never come back pointing at somebody else's punch.
    """
    dia = getattr(instance.prezensa, 'data', None) or data_ohin()
    return naran_foto_uniku(f'prezensa/{dia:%Y/%m}', filename)


class Fulan(models.IntegerChoices):
    """Months as printed on the sheet header (FULAN JULLU 2026)."""

    JANEIRU = 1, _('Janeiru')
    FEVEREIRU = 2, _('Fevereiru')
    MARSU = 3, _('Marsu')
    ABRIL = 4, _('Abril')
    MAIU = 5, _('Maiu')
    JUÑU = 6, _('Juñu')
    JULLU = 7, _('Jullu')
    AGOSTU = 8, _('Agostu')
    SETEMBRU = 9, _('Setembru')
    OUTUBRU = 10, _('Outubru')
    NOVEMBRU = 11, _('Novembru')
    DEZEMBRU = 12, _('Dezembru')


class Sesaun(models.TextChoices):
    """The two blocks of the day printed on the sheet."""

    DADER = 'DADER', _('Dader')
    LOROKRAIK = 'LOROKRAIK', _('Lorokraik')


class Tipu(models.TextChoices):
    """Arrival or departure -- TAMA / FILA on the sheet."""

    TAMA = 'TAMA', _('Tama')
    FILA = 'FILA', _('Fila')


#: LORON column -- Python's date.weekday() index -> label used on the sheet.
LORON = {
    0: _('Segunda-feira'),
    1: _('Tersa-feira'),
    2: _('Quarta-feira'),
    3: _('Quinta-feira'),
    4: _('Sexta-feira'),
    5: _('Sabado'),
    6: _('Domingu'),
}


def loron_servisu(fulan, tinan):
    """
    Every working day of a month, in order. Sundays are left out because the
    printed sheet skips them -- Saturday is a half day, Sunday is not a day.
    """
    _dahuluk, loron_hotu = monthrange(tinan, fulan)
    return [
        date(tinan, fulan, loron)
        for loron in range(1, loron_hotu + 1)
        if date(tinan, fulan, loron).weekday() != 6
    ]


def semana_husi(data):
    """
    Which week of its own month a date falls in, counting from Monday, so a
    week never straddles two numbers on the same sheet.
    """
    inisiu_fulan = date(data.year, data.month, 1).weekday()
    return (data.day + inisiu_fulan - 1) // 7 + 1


def data_ohin():
    """
    Today in Dili. The single source of "which day is it" for the whole app --
    views and managers go through here rather than each calling the clock, so
    a punch and the report that reads it can never disagree about the date.
    """
    return timezone.localdate()


class ListaPrezensa(models.Model):
    """
    "LISTA PREZENSA BA PROFESÓR/A ETI DILI" -- one printed sheet, i.e. one
    teacher for one month. Carries the header block of the form (Naran, Kargu,
    Fulan/Tinan); the day-by-day grid lives in :class:`Prezensa`.
    """

    profesor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='lista_prezensa',
        verbose_name=_('profesór/a'),
    )
    # The only field copied from the user instead of read through `profesor`:
    # KARGU is frozen when the sheet is issued, because a promotion must not
    # rewrite the title printed on the sheets of previous months. Everything
    # else (naran, foto, ...) is read from `profesor` and never duplicated.
    # Filled in save(); do not set it from callers.
    kargu = models.CharField(_('kargu'), max_length=120, blank=True)

    fulan = models.PositiveSmallIntegerField(_('fulan'), choices=Fulan.choices)
    tinan = models.PositiveSmallIntegerField(
        _('tinan'),
        validators=[MinValueValidator(2000), MaxValueValidator(2100)],
    )

    kriadu_iha = models.DateTimeField(_('kriadu iha'), auto_now_add=True)
    atualiza_iha = models.DateTimeField(_('atualiza iha'), auto_now=True)

    class Meta:
        verbose_name = _('lista prezensa')
        verbose_name_plural = _('lista prezensa')
        ordering = ['-tinan', '-fulan', 'profesor__naran_kompletu']
        constraints = [
            models.UniqueConstraint(
                fields=['profesor', 'fulan', 'tinan'],
                name='unique_lista_prezensa_profesor_fulan_tinan',
            ),
        ]

    def __str__(self):
        return f'{self.profesor} - {self.get_fulan_display()} {self.tinan}'

    def save(self, *args, **kwargs):
        if not self.kargu and self.profesor_id:
            self.kargu = self.profesor.kargu
        super().save(*args, **kwargs)


class PrezensaManager(models.Manager):
    def ba_loron(self, profesor, data=None):
        """
        Return (creating if needed) the row for `profesor` on `data`, together
        with the monthly sheet that owns it. This is what the mobile app hits
        on the first punch of the day.
        """
        data = data or data_ohin()
        lista, _created = ListaPrezensa.objects.get_or_create(
            profesor=profesor,
            fulan=data.month,
            tinan=data.year,
        )
        prezensa, _created = self.get_or_create(lista=lista, data=data)
        return prezensa


class Prezensa(models.Model):
    """
    One row of the grid: DATA / LORON plus OBS.

    The four time columns of the paper book are not stored here -- each punch
    is a :class:`Marka`, because a punch now carries evidence (photo and GPS)
    that has to stay attached to the punch it belongs to. The `oras_*`
    properties below rebuild the printed layout from those punches.
    """

    class Status(models.TextChoices):
        # English keys, Tetun labels: the stored value is API contract, the
        # label is what users read.
        PRESENT = 'PRESENT', _('Prezente')
        ABSENT = 'ABSENT', _('Falta')
        LEAVE = 'LEAVE', _('Lisensa')
        MISSION = 'MISSION', _('Misaun')
        HOLIDAY = 'HOLIDAY', _('Feriadu')

    #: Re-exported so callers do not need to import the module-level choices.
    Sesaun = Sesaun
    Tipu = Tipu

    #: Scheduled times printed in the column headers.
    ORAS_DADER_TAMA = time(8, 0)
    ORAS_DADER_FILA = time(12, 0)
    ORAS_LOROKRAIK_TAMA = time(13, 30)
    ORAS_LOROKRAIK_FILA = time(17, 30)

    #: A punch at or after this time belongs to the afternoon session.
    LIMITE_SESAUN = time(13, 0)

    lista = models.ForeignKey(
        ListaPrezensa,
        on_delete=models.CASCADE,
        related_name='prezensa',
        verbose_name=_('lista prezensa'),
    )
    data = models.DateField(_('data'))

    status = models.CharField(
        _('status'),
        max_length=10,
        choices=Status.choices,
        default=Status.PRESENT,
    )
    # OBS
    obs = models.TextField(_('obs'), blank=True)

    objects = PrezensaManager()

    class Meta:
        verbose_name = _('prezensa')
        verbose_name_plural = _('prezensa')
        ordering = ['data']
        constraints = [
            models.UniqueConstraint(
                fields=['lista', 'data'],
                name='unique_prezensa_lista_data',
            ),
        ]

    def __str__(self):
        return f'{self.data} - {self.lista.profesor}'

    @property
    def loron(self):
        """LORON column -- weekday name in Tetun."""
        return LORON[self.data.weekday()]

    @property
    def sabadu(self):
        """Saturdays have no afternoon session on the printed sheet."""
        return self.data.weekday() == 5

    # -- The printed grid, rebuilt from the punches ---------------------------

    def marka_ba(self, sesaun, tipu):
        """The punch for one cell of the grid, or None if it was never made."""
        for marka in self.marka.all():
            if marka.sesaun == sesaun and marka.tipu == tipu:
                return marka
        return None

    def oras_ba(self, sesaun, tipu):
        marka = self.marka_ba(sesaun, tipu)
        return marka.oras if marka else None

    @property
    def oras_dader_tama(self):
        return self.oras_ba(Sesaun.DADER, Tipu.TAMA)

    @property
    def oras_dader_fila(self):
        return self.oras_ba(Sesaun.DADER, Tipu.FILA)

    @property
    def oras_lorokraik_tama(self):
        return self.oras_ba(Sesaun.LOROKRAIK, Tipu.TAMA)

    @property
    def oras_lorokraik_fila(self):
        return self.oras_ba(Sesaun.LOROKRAIK, Tipu.FILA)

    # -- Check in / check out -------------------------------------------------

    @classmethod
    def sesaun_ba(cls, oras):
        """Which session a punch made at `oras` belongs to."""
        return Sesaun.DADER if oras < cls.LIMITE_SESAUN else Sesaun.LOROKRAIK

    def checkin(self, **evidensia):
        """
        Record the arrival punch (TAMA) for the current session. The evidence
        (`foto`, `latitude`, `longitude`, optional `presizaun`) replaces the
        handwritten signature of the paper book.
        """
        return self._rejistu(Tipu.TAMA, **evidensia)

    def checkout(self, **evidensia):
        """Record the departure punch (FILA) for the current session."""
        return self._rejistu(Tipu.FILA, **evidensia)

    def _rejistu(self, tipu, foto, latitude, longitude, presizaun=None,
                 oras=None, sesaun=None):
        oras = oras or timezone.localtime().time()
        sesaun = sesaun or self.sesaun_ba(oras)

        if self.marka_ba(sesaun, tipu) is not None:
            raise ValidationError(
                _('Prezensa ne\'e rejistu tiha ona iha %(oras)s.'),
                code='duplicate',
                params={'oras': self.oras_ba(sesaun, tipu)},
            )
        if tipu == Tipu.FILA and self.marka_ba(sesaun, Tipu.TAMA) is None:
            raise ValidationError(
                _('Tenke halo checkin molok checkout.'),
                code='no_checkin',
            )
        if self.sabadu and sesaun == Sesaun.LOROKRAIK:
            raise ValidationError(
                _('Loron Sabadu la iha sesaun lorokraik.'),
                code='no_session',
            )

        # The teacher has to be at the school to punch. `iha_eskola` is None
        # when no coordinates are configured, and that must not block anyone.
        if settings.ESKOLA_OBRIGA_FATIN:
            distansia = distansia_husi_eskola(latitude, longitude)
            if distansia is not None and distansia > settings.ESKOLA_RAIU_METRU:
                raise ValidationError(
                    _('Ita dook liu husi eskola (%(distansia)s m). '
                      'Presiza besik eskola atu marka prezensa.'),
                    code='dook_husi_eskola',
                    params={'distansia': round(distansia)},
                )

        marka = self.marka.create(
            sesaun=sesaun,
            tipu=tipu,
            oras=oras,
            foto=foto,
            latitude=latitude,
            longitude=longitude,
            presizaun=presizaun,
        )
        if self.status != self.Status.PRESENT:
            self.status = self.Status.PRESENT
            self.save(update_fields=['status'])

        # Drop the cached punches so the `oras_*` properties see the new one.
        self.refresh_from_db()
        return marka


class Marka(models.Model):
    """
    One punch: the moment a teacher pressed Check in or Check out, with the
    evidence collected at that moment.

    Nothing here is editable by the teacher -- the time comes from the server
    and the coordinates from the device, so the row is the proof that the
    signature used to be on paper.
    """

    prezensa = models.ForeignKey(
        Prezensa,
        on_delete=models.CASCADE,
        related_name='marka',
        verbose_name=_('prezensa'),
    )
    sesaun = models.CharField(_('sesaun'), max_length=10, choices=Sesaun.choices)
    tipu = models.CharField(_('tipu'), max_length=4, choices=Tipu.choices)

    oras = models.TimeField(_('oras'))
    rejistu_iha = models.DateTimeField(_('rejistu iha'), auto_now_add=True)

    # Evidence: the photo taken at the punch and where the device was.
    foto = models.ImageField(_('foto'), upload_to=foto_marka)
    latitude = models.DecimalField(
        _('latitude'),
        max_digits=9,
        decimal_places=6,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    longitude = models.DecimalField(
        _('longitude'),
        max_digits=9,
        decimal_places=6,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )
    #: Accuracy radius reported by the device, in metres.
    presizaun = models.FloatField(_('presizaun'), blank=True, null=True)

    # Derived from the coordinates when the punch is saved, so reviewing a
    # month does not mean recomputing distances for every row.
    distansia_metru = models.FloatField(_('distánsia (m)'), blank=True, null=True)
    iha_eskola = models.BooleanField(_('iha eskola'), blank=True, null=True)

    class Meta:
        verbose_name = _('marka')
        verbose_name_plural = _('marka')
        ordering = ['prezensa__data', 'oras']
        constraints = [
            models.UniqueConstraint(
                fields=['prezensa', 'sesaun', 'tipu'],
                name='unique_marka_prezensa_sesaun_tipu',
            ),
        ]

    def __str__(self):
        return f'{self.prezensa.data} {self.get_sesaun_display()} {self.get_tipu_display()} {self.oras}'

    @property
    def kolumna(self):
        """
        The column of the paper book this punch fills: ORAS_DADER_TAMA,
        ORAS_DADER_FILA, ORAS_LOROKRAIK_TAMA or ORAS_LOROKRAIK_FILA.
        """
        return f'ORAS_{self.sesaun}_{self.tipu}'

    @property
    def oras_orariu(self):
        """The scheduled time printed in that column's header."""
        return getattr(Prezensa, self.kolumna)

    @property
    def atrazadu(self):
        """Whether an arrival punch was made after its scheduled time."""
        if self.tipu != Tipu.TAMA:
            return None
        return self.oras > self.oras_orariu

    def save(self, *args, **kwargs):
        if self.latitude is not None and self.longitude is not None:
            self.distansia_metru = distansia_husi_eskola(self.latitude, self.longitude)
            self.iha_eskola = iha_eskola(self.latitude, self.longitude)
        super().save(*args, **kwargs)
