from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import EhAdmin

from .models import (
    LORON,
    Fulan,
    ListaPrezensa,
    Marka,
    Prezensa,
    data_ohin,
    loron_servisu,
    semana_husi,
)
from .serializers import (
    ListaPrezensaSerializer,
    MarkaPrezensaSerializer,
    MarkaSerializer,
    PrezensaOhinSerializer,
    PrezensaProfesorLoronLigeruSerializer,
    PrezensaProfesorLoronSerializer,
    PrezensaProfesorSerializer,
    PrezensaSerializer,
    StatusHasaiSerializer,
    StatusRejistuSerializer,
)


def profesores_relatoriu():
    """
    Everyone who appears on attendance reports: teaching staff AND the
    administration -- the director signs the book like everyone else, so
    ADMIN accounts keep a sheet too. Students never appear.
    """
    User = get_user_model()
    return (
        User.objects
        .filter(role__in=[User.Role.PROFESSOR, User.Role.ADMIN], is_active=True)
        .order_by('naran_kompletu')
    )


class PrezensaViewSet(mixins.ListModelMixin,
                      mixins.RetrieveModelMixin,
                      viewsets.GenericViewSet):
    """
    Daily attendance for the logged-in teacher: the home screen (`ohin`) and
    the two buttons that write to it.
    """

    serializer_class = PrezensaSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        return (
            Prezensa.objects
            .filter(lista__profesor=self.request.user)
            .select_related('lista', 'lista__profesor')
            .prefetch_related('marka')
        )

    @action(detail=False, methods=['get'])
    def ohin(self, request):
        """Today's row, created on first access."""
        prezensa = Prezensa.objects.ba_loron(request.user)
        serializer = PrezensaOhinSerializer(prezensa, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'], url_path='istoria')
    def istoria(self, request):
        """
        One month of attendance for the logged-in teacher, laid out like the
        paper sheet: every working day of the month, whether it was marked or
        not, grouped into weeks.

        Query parameters, all optional:
          fulan    -- month 1..12   (default: this month)
          tinan    -- year          (default: this year)
          semana   -- 1..6, to narrow the answer to a single week
          profesor -- admin only: another teacher's sheet instead of your own
        """
        try:
            fulan, tinan, semana = self._periodu(request)
        except ValueError as exc:
            return Response(
                {'detail': str(exc), 'code': 'invalid_period'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        profesor_param = request.query_params.get('profesor')
        if profesor_param:
            # Somebody else's sheet is the administration's to read, not a
            # colleague's.
            if not EhAdmin().has_permission(request, self):
                return Response(
                    {'detail': EhAdmin.message},
                    status=status.HTTP_403_FORBIDDEN,
                )
            try:
                alvo = get_user_model().objects.get(pk=int(profesor_param))
            except (TypeError, ValueError, get_user_model().DoesNotExist):
                return Response(
                    {'detail': 'Profesór la eziste.', 'code': 'invalid_profesor'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            alvo = request.user

        prezensa_fulan = {
            prezensa.data: prezensa
            for prezensa in (
                Prezensa.objects
                .filter(
                    lista__profesor=alvo,
                    data__year=tinan,
                    data__month=fulan,
                )
                .select_related('lista', 'lista__profesor')
                .prefetch_related('marka')
            )
        }

        loron = [
            self._loron(data, prezensa_fulan.get(data), alvo, request)
            for data in loron_servisu(fulan, tinan)
            if semana is None or semana_husi(data) == semana
        ]

        marka_ona = [item for item in loron if item['marka']]
        return Response({
            'profesor': alvo.naran_kompletu,
            # The sheet's header block is Naran + Kargu.
            'kargu': alvo.kargu,
            'fulan': fulan,
            'fulan_display': Fulan(fulan).label,
            'tinan': tinan,
            'semana': semana,
            'rezumu': {
                'loron_servisu': len(loron),
                'marka_ona': len(marka_ona),
                'seidauk_marka': len(loron) - len(marka_ona),
                'marka_total': sum(len(item['marka']) for item in marka_ona),
                'atrazadu': sum(
                    1
                    for item in marka_ona
                    for marka in item['marka']
                    if marka['atrazadu']
                ),
            },
            'loron': loron,
        })

    @staticmethod
    def _periodu(request):
        """Read fulan/tinan/semana off the query string, with today's defaults."""
        ohin = data_ohin()

        def numeru(naran, omisaun, minimu, maksimu):
            valor = request.query_params.get(naran)
            if valor in (None, ''):
                return omisaun
            try:
                valor = int(valor)
            except (TypeError, ValueError):
                raise ValueError(f'{naran}: presiza numeru.')
            if not minimu <= valor <= maksimu:
                raise ValueError(f'{naran}: presiza entre {minimu} no {maksimu}.')
            return valor

        return (
            numeru('fulan', ohin.month, 1, 12),
            numeru('tinan', ohin.year, 2000, 2100),
            numeru('semana', None, 1, 6),
        )

    def _loron(self, data, prezensa, profesor, request):
        """One row of the sheet -- an empty one when nothing was marked."""
        if prezensa is not None:
            linha = PrezensaSerializer(prezensa, context={'request': request}).data
        else:
            linha = {
                'id': None,
                'profesor': profesor.naran_kompletu,
                'data': data,
                'loron': LORON[data.weekday()],
                'oras_dader_tama': None,
                'oras_dader_fila': None,
                'oras_lorokraik_tama': None,
                'oras_lorokraik_fila': None,
                'status': None,
                'status_display': None,
                'obs': '',
                'marka': [],
            }
        linha['semana'] = semana_husi(data)
        linha['sabadu'] = data.weekday() == 5
        return linha

    @action(
        detail=False,
        methods=['get'],
        url_path='ohin-hotu',
        permission_classes=[IsAuthenticated, EhAdmin],
    )
    def ohin_hotu(self, request):
        """
        Today's attendance for every teacher -- the administration's daily
        report. Teachers who have not punched are listed too, with a null day,
        because that absence is the whole reason to open this screen.
        """
        data = data_ohin()
        profesores = profesores_relatoriu()
        # One query for the whole school, then matched in memory, so the report
        # does not run a query per teacher.
        prezensa_ohin = {
            prezensa.lista.profesor_id: prezensa
            for prezensa in (
                Prezensa.objects
                .filter(data=data, lista__profesor__in=profesores)
                .select_related('lista')
                .prefetch_related('marka')
            )
        }

        liña = [
            {
                'profesor': profesor,
                'prezensa': prezensa_ohin.get(profesor.pk),
                'marka_ona': bool(
                    prezensa_ohin.get(profesor.pk)
                    and prezensa_ohin[profesor.pk].marka.all()
                ),
            }
            for profesor in profesores
        ]

        marka_ona = sum(1 for item in liña if item['marka_ona'])
        return Response({
            'data': data,
            'loron': LORON[data.weekday()],
            'rezumu': {
                'total': len(liña),
                'marka_ona': marka_ona,
                'seidauk_marka': len(liña) - marka_ona,
            },
            'profesor': PrezensaProfesorSerializer(
                liña, many=True, context={'request': request}
            ).data,
        })

    @action(
        detail=False,
        methods=['get'],
        url_path='hotu',
        permission_classes=[IsAuthenticated, EhAdmin],
    )
    def hotu(self, request):
        """
        Attendance for every teacher over a day, a week or a month -- the
        dashboard's grid and report source (plan R2). One line per teacher per
        working day, empty days included, teacher-major then date-ascending.
        `?marka=false` omits the nested punches for a light first load.
        """
        try:
            periodu, loron_lista = self._periodu_hotu(request)
        except ValueError as exc:
            return Response(
                {'detail': str(exc), 'code': 'invalid_period'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        profesores = profesores_relatoriu()
        profesor_param = request.query_params.get('profesor')
        if profesor_param:
            try:
                profesores = profesores.filter(pk=int(profesor_param))
            except (TypeError, ValueError):
                return Response(
                    {'detail': 'profesor: presiza numeru.', 'code': 'invalid_profesor'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        prezensa_mapa = {
            (prezensa.lista.profesor_id, prezensa.data): prezensa
            for prezensa in (
                Prezensa.objects
                .filter(data__in=loron_lista, lista__profesor__in=profesores)
                .select_related('lista')
                .prefetch_related('marka')
            )
        }

        linha = []
        for profesor in profesores:
            for loron in loron_lista:
                prezensa = prezensa_mapa.get((profesor.pk, loron))
                linha.append({
                    'profesor': profesor,
                    'data': loron,
                    'prezensa': prezensa,
                    'marka_ona': bool(prezensa and prezensa.marka.all()),
                })

        serializer_class = (
            PrezensaProfesorLoronLigeruSerializer
            if request.query_params.get('marka') == 'false'
            else PrezensaProfesorLoronSerializer
        )
        return Response({
            **periodu,
            'profesor': serializer_class(
                linha, many=True, context={'request': request}
            ).data,
        })

    def _periodu_hotu(self, request):
        """`?data=` takes a single day; otherwise fulan/tinan/semana as istoria."""
        data_param = request.query_params.get('data')
        if data_param:
            try:
                dia = date.fromisoformat(data_param)
            except ValueError:
                raise ValueError('data: presiza formatu YYYY-MM-DD.')
            return {'data': dia, 'loron': LORON[dia.weekday()]}, [dia]

        fulan, tinan, semana = self._periodu(request)
        loron_lista = [
            dia for dia in loron_servisu(fulan, tinan)
            if semana is None or semana_husi(dia) == semana
        ]
        return {'fulan': fulan, 'tinan': tinan, 'semana': semana}, loron_lista

    @action(
        detail=False,
        methods=['post', 'delete'],
        url_path='status',
        permission_classes=[IsAuthenticated, EhAdmin],
        parser_classes=[JSONParser, MultiPartParser, FormParser],
    )
    def status(self, request):
        if request.method == 'POST':
            return self._status_rejistu(request)
        return self._status_hasai(request)

    def _status_rejistu(self, request):
        """
        Hand-write LEAVE / MISSION / HOLIDAY / ABSENT plus OBS over a date
        range (plan R5). Sundays are skipped. A day that already holds punches
        blocks the WHOLE request with `iha_marka` -- Marka rows are evidence
        and must never be silently buried under a leave.
        """
        payload = StatusRejistuSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        dados = payload.validated_data

        profesor = get_user_model().objects.filter(pk=dados['profesor']).first()
        if profesor is None:
            return Response(
                {'detail': 'Profesór la eziste.', 'code': 'invalid_profesor'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        husi, too = dados['husi'], dados['too']
        if husi > too:
            return Response(
                {'detail': "husi tenke molok ka hanesan to'o.", 'code': 'invalid_period'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if (too - husi).days > 366:
            return Response(
                {'detail': 'Periodu naruk liu tinan ida.', 'code': 'invalid_period'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        dias = [
            husi + timedelta(days=n)
            for n in range((too - husi).days + 1)
            if (husi + timedelta(days=n)).weekday() != 6
        ]

        with transaction.atomic():
            konflitu = sorted(set(
                Marka.objects
                .filter(prezensa__lista__profesor=profesor, prezensa__data__in=dias)
                .values_list('prezensa__data', flat=True)
            ))
            if konflitu:
                return Response(
                    {
                        'detail': "Loron balun iha marka ona; la bele taka ho status.",
                        'code': 'iha_marka',
                        'loron': [dia.isoformat() for dia in konflitu],
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            for dia in dias:
                prezensa = Prezensa.objects.ba_loron(profesor, dia)
                prezensa.status = dados['status']
                prezensa.obs = dados['obs']
                prezensa.save(update_fields=['status', 'obs'])

        return Response(
            {
                'detail': 'Status rejistu ho susesu.',
                'profesor': profesor.pk,
                'status': dados['status'],
                'husi': husi,
                'too': too,
                'loron': [dia.isoformat() for dia in dias],
                'total': len(dias),
            },
            status=status.HTTP_201_CREATED,
        )

    def _status_hasai(self, request):
        """
        Remove a hand-written day so it returns to "no record" (plan R6).
        Only valid when the day holds no punches and its status is not
        PRESENT -- punches are evidence and cannot be deleted from here.
        """
        payload = StatusHasaiSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        prezensa = (
            Prezensa.objects
            .filter(
                lista__profesor_id=payload.validated_data['profesor'],
                data=payload.validated_data['data'],
            )
            .prefetch_related('marka')
            .first()
        )
        if prezensa is None:
            return Response(
                {'detail': 'Rejistu la eziste.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if prezensa.marka.all() or prezensa.status == Prezensa.Status.PRESENT:
            return Response(
                {
                    'detail': "Loron ne'e iha marka ka status PRESENT; la bele hasai.",
                    'code': 'iha_marka',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        prezensa.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['post'], url_path='checkin', url_name='checkin')
    def checkin(self, request):
        """
        Arrival punch. Writes ORAS_DADER_TAMA before 13:00 and
        ORAS_LOROKRAIK_TAMA after it, unless `sesaun` says otherwise.
        """
        return self._marka(request, tama=True)

    @action(detail=False, methods=['post'], url_path='checkout', url_name='checkout')
    def checkout(self, request):
        """
        Departure punch. Writes ORAS_DADER_FILA before 13:00 and
        ORAS_LOROKRAIK_FILA after it, unless `sesaun` says otherwise.
        """
        return self._marka(request, tama=False)

    def _marka(self, request, tama):
        payload = MarkaPrezensaSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        prezensa = Prezensa.objects.ba_loron(request.user)
        evidensia = payload.validated_data
        try:
            if tama:
                marka = prezensa.checkin(**evidensia)
            else:
                marka = prezensa.checkout(**evidensia)
        except ValidationError as exc:
            erru = {'detail': exc.messages[0], 'code': exc.code}
            # e.g. how far off the teacher is, so the app can say it plainly.
            erru.update(getattr(exc, 'params', None) or {})
            return Response(erru, status=status.HTTP_400_BAD_REQUEST)

        data = PrezensaOhinSerializer(prezensa, context={'request': request}).data
        # The punch just made, so the app does not have to find it in `marka`.
        data['marka_foun'] = MarkaSerializer(marka, context={'request': request}).data
        return Response(data, status=status.HTTP_201_CREATED)


class ListaPrezensaViewSet(mixins.ListModelMixin,
                           mixins.RetrieveModelMixin,
                           viewsets.GenericViewSet):
    """Monthly sheets of the logged-in teacher -- the "Historia" tab."""

    serializer_class = ListaPrezensaSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return (
            ListaPrezensa.objects
            .filter(profesor=self.request.user)
            .select_related('profesor')
            .prefetch_related('prezensa__marka')
        )


class KonfigView(APIView):
    """
    The scheduled times and geofence settings the dashboard's Konfig panel
    shows (plan R8). The school's coordinates are deliberately excluded --
    publishing the exact geofence centre helps nobody but a spoofer.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            'oras_dader_tama': Prezensa.ORAS_DADER_TAMA,
            'oras_dader_fila': Prezensa.ORAS_DADER_FILA,
            'oras_lorokraik_tama': Prezensa.ORAS_LOROKRAIK_TAMA,
            'oras_lorokraik_fila': Prezensa.ORAS_LOROKRAIK_FILA,
            'limite_sesaun': Prezensa.LIMITE_SESAUN,
            'eskola_raiu_metru': settings.ESKOLA_RAIU_METRU,
            'eskola_obriga_fatin': settings.ESKOLA_OBRIGA_FATIN,
        })


class MarkaFotoView(APIView):
    """
    Download one punch photo under a readable name.

    The file on disk carries an unguessable uuid, because MEDIA_ROOT is served
    with no authentication -- a name built from the teacher and the date would
    let anyone who sees one URL walk to every other teacher's selfie. This
    route checks the token first, then hands the same bytes over as
    `punch_juliao-martins_checkin_2026-08-10_dader.jpg`.

    A teacher may fetch their own punches; an admin may fetch anyone's.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        marka = get_object_or_404(
            Marka.objects.select_related('prezensa__lista__profesor'), pk=pk
        )

        eh_nia_rasik = marka.prezensa.lista.profesor_id == request.user.pk
        if not (eh_nia_rasik or EhAdmin().has_permission(request, self)):
            return Response(
                {'detail': EhAdmin.message, 'code': 'la_iha_permisaun'},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            ficheiru = marka.foto.open('rb')
        except (FileNotFoundError, ValueError):
            # The row survives but the file is gone -- say so plainly rather
            # than serving a broken download.
            return Response(
                {'detail': 'Foto la iha iha servidor.', 'code': 'foto_lakon'},
                status=status.HTTP_404_NOT_FOUND,
            )

        return FileResponse(
            ficheiru, as_attachment=True, filename=marka.naran_foto_download
        )
