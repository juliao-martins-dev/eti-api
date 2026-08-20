import logging

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils.crypto import get_random_string
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import Throttled
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from attendance.models import Marka

from .models import User, bele_hasai_foto
from .permissions import EhAdmin
from .serializers import (
    FotoSerializer,
    LoginSerializer,
    LogoutSerializer,
    ProfesorAtualizaSerializer,
    ProfesorHasaiSerializer,
    ProfesorKriaSerializer,
    ProfesorResetPasswordSerializer,
    ProfesorRosterSerializer,
    TrokaPasswordSerializer,
    UserSerializer,
)

logger = logging.getLogger(__name__)


def kode_erru(errors):
    """
    The `code` a serializer's `validate()` attached to its ValidationError.

    DRF rewraps the dict we raised, so the code arrives as
    `{'code': [ErrorDetail('password_la_hanesan')]}` -- a list, which is why
    reading `errors['code']` directly never matched and the callers fell back
    to searching the stringified dict. That fallback also matched an error
    whose *message* merely contained the word.
    """
    valor = errors.get('code')
    if isinstance(valor, (list, tuple)):
        valor = valor[0] if valor else None
    return str(valor) if valor is not None else None


def taka_sesaun(user):
    """
    Blacklist every refresh token outstanding for `user`, returning how many
    were still live.

    Shared by the admin reset and the self-service change: both happen because
    a password stopped being trustworthy, and a session opened under the old
    one must not outlive it.
    """
    taka = 0
    for token in OutstandingToken.objects.filter(user=user):
        _blacklisted, kriadu = BlacklistedToken.objects.get_or_create(token=token)
        taka += int(kriadu)
    return taka


def erru_password_fraku(senha, user):
    """
    Run Django's configured validators -- length, common passwords, all
    numeric, similarity to the e-mail and name -- and return the coded 400 to
    answer with, or None when the password is good enough.
    """
    try:
        validate_password(senha, user=user)
    except DjangoValidationError as exc:
        return Response(
            {
                'detail': ' '.join(exc.messages),
                'code': 'password_fraku',
                'erros': exc.messages,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    return None


class LoginBarakLiu(Throttled):
    """
    The 429 in Tetun.

    DRF's own wording is English, and this is the one error a teacher standing
    at the door will actually see -- the same reason `accounts.validators`
    exists. `wait` is filled in by DRF from the throttle.
    """

    default_detail = 'Koko login barak liu.'
    extra_detail_singular = 'Favor hein segundu {wait} molok koko fali.'
    extra_detail_plural = 'Favor hein segundu {wait} molok koko fali.'
    default_code = 'login_barak_liu'


class LoginView(TokenObtainPairView):
    """
    POST email + password -> {access, refresh, user}.

    The one route that takes a password from a caller holding no token, so the
    one route worth rate limiting: everything else already requires a valid
    access token to reach. The rate is `THROTTLE_LOGIN` in .env, because the
    whole school shares one public IP and a limit that is right for the
    internet can be wrong for a staffroom at eight in the morning.
    """

    serializer_class = LoginSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'login'

    def throttled(self, request, wait):
        raise LoginBarakLiu(wait)


class LogoutView(APIView):
    """
    POST the refresh token to blacklist it, so it can no longer be exchanged
    for a new access token.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = LogoutSerializer

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            RefreshToken(serializer.validated_data['refresh']).blacklist()
        except TokenError as exc:
            return Response(
                {'detail': str(exc), 'code': 'token_not_valid'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {'detail': 'Sai ho susesu.'},
            status=status.HTTP_205_RESET_CONTENT,
        )


class MeView(RetrieveUpdateAPIView):
    """
    The logged-in teacher's own profile.

    GET returns it; PATCH replaces the photo. PUT is deliberately not allowed —
    it would imply the whole profile is the client's to replace, and only the
    photo is.
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]
    http_method_names = ['get', 'patch', 'head', 'options']

    def get_object(self):
        return self.request.user

    def get_serializer_class(self):
        if self.request.method == 'PATCH':
            return FotoSerializer
        return UserSerializer

    def update(self, request, *args, **kwargs):
        # Not `partial=True`: DRF's partial mode makes every field optional,
        # and with `foto` as the only field a PATCH without one would be a
        # silent no-op returning 200. The photo is the request.
        serializer = self.get_serializer(self.get_object(), data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        # Answer with the whole profile, so the app can redraw its header from
        # this one response instead of following up with a GET.
        return Response(
            UserSerializer(
                self.get_object(), context=self.get_serializer_context()
            ).data
        )


class ProfesorViewSet(mixins.ListModelMixin,
                      mixins.RetrieveModelMixin,
                      viewsets.GenericViewSet):
    """
    The dashboard's teacher roster (plan R1/R3/R4).

    Lists **teachers and admins**, matching the reports
    (`attendance.views.profesores_relatoriu`) -- the director keeps a sheet and
    an account like everyone else, so hiding them here only made the roster
    disagree with every other screen. Deactivated accounts are included, since
    the dashboard badges them "Dezativadu" and offers reactivation.

    Leaving the school is PATCH {"is_active": false}, which keeps the sheets;
    DELETE is the irreversible one and takes the whole history with it. Neither
    DELETE nor the password reset may target an ADMIN -- see `_eh_admin`.
    """

    serializer_class = ProfesorRosterSerializer
    permission_classes = [IsAuthenticated, EhAdmin]
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_queryset(self):
        return User.objects.filter(
            role__in=[User.Role.PROFESSOR, User.Role.ADMIN]
        )

    @staticmethod
    def _eh_admin(alvo):
        """
        An admin account is off limits to the roster's destructive actions.
        Until now they were simply invisible here; with the list widened, the
        guard has to be said out loud or one admin could remove another.
        """
        return alvo.is_staff or alvo.role == User.Role.ADMIN

    def _duplikadu(self, data, instance=None):
        """
        The coded 400 the dashboard maps onto its two duplicate toasts.
        Checked against every account, not just teachers, since both columns
        are unique across the whole table.
        """
        existente = User.objects.all()
        if instance is not None:
            existente = existente.exclude(pk=instance.pk)

        numeru = data.get('numeru_id')
        try:
            if numeru not in (None, '') and existente.filter(numeru_id=int(numeru)).exists():
                return Response(
                    {'detail': "Numeru ID ne'e uza tiha ona.", 'code': 'duplicate_numeru'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except (TypeError, ValueError):
            pass  # not a number -- the serializer reports the malformed field

        # `iexact`, because Django's normalize_email only lowercases the
        # domain: "P.Prof@eti.tl" and "p.prof@eti.tl" were two accounts, and
        # since login matches the address exactly, the teacher who typed the
        # other case simply could not get in.
        email = data.get('email')
        if email and existente.filter(email__iexact=email).exists():
            return Response(
                {'detail': "Email ne'e uza tiha ona.", 'code': 'duplicate_email'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return None

    def create(self, request):
        duplikadu = self._duplikadu(request.data)
        if duplikadu:
            return duplikadu

        serializer = ProfesorKriaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # E-mail delivery does not exist yet, so the initial password is
        # returned once in the 201 body for the admin to hand over (plan R3).
        senha = get_random_string(12)
        profesor = User.objects.create_user(password=senha, **serializer.validated_data)

        body = self.get_serializer(profesor).data
        body['password_inisial'] = senha
        return Response(body, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        profesor = self.get_object()
        duplikadu = self._duplikadu(request.data, instance=profesor)
        if duplikadu:
            return duplikadu

        serializer = ProfesorAtualizaSerializer(
            profesor, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)

        # Deactivation is as destructive as the two guarded actions and was the
        # only way to reach either forbidden outcome: an admin could switch
        # their own account off and be refused at the very next request, with
        # no way back except manage.py on the server. Read from validated_data
        # so "false", 0 and False are all recognised.
        if serializer.validated_data.get('is_active') is False:
            if profesor.pk == request.user.pk:
                return Response(
                    {
                        'detail': 'La bele dezativa konta rasik.',
                        'code': 'rasik',
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            if self._eh_admin(profesor):
                return Response(
                    {
                        'detail': 'La bele dezativa konta administradór. '
                                  'Muda role ba PROFESSOR uluk.',
                        'code': 'eh_admin',
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

        serializer.save()
        return Response(self.get_serializer(profesor).data)

    @action(detail=True, methods=['post'], url_path='reset-password')
    def reset_password(self, request, pk=None):
        """
        The admin sets a new password for a teacher who lost theirs.

        There is no self-service reset -- no e-mail delivery, no reset link --
        so the teacher contacts the admin and the admin hands the new password
        over in person. The plain text is never stored and never returned: the
        admin typed it and already has it.
        """
        alvo = self.get_object()

        if alvo.pk == request.user.pk:
            return Response(
                {
                    'detail': "La bele troka password rasik iha ne'e.",
                    'code': 'rasik',
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if self._eh_admin(alvo):
            return Response(
                {
                    'detail': 'La bele troka password ba konta administradór.',
                    'code': 'eh_admin',
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        payload = ProfesorResetPasswordSerializer(data=request.data)
        if not payload.is_valid():
            # The "two fields differ" case carries its own code; anything else
            # is a plain missing-field error.
            if kode_erru(payload.errors) == 'password_la_hanesan':
                return Response(
                    {'detail': 'Password rua la hanesan.', 'code': 'password_la_hanesan'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(
                {
                    'detail': 'Presiza hatama password foun dala rua.',
                    'code': 'password_presiza',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        senha = payload.validated_data['password_foun']
        fraku = erru_password_fraku(senha, alvo)
        if fraku:
            return fraku

        alvo.set_password(senha)
        alvo.save(update_fields=['password'])

        # Old sessions must not survive a reset: a phone already logged in
        # would keep working, which defeats the point when the reset is
        # because the account was compromised.
        sesaun = taka_sesaun(alvo)

        logger.warning(
            'password reset: actor=id=%s alvo=id=%s numeru_id=%s sesaun_taka=%s',
            request.user.pk, alvo.pk, alvo.numeru_id, sesaun,
        )

        return Response({
            'detail': f'Password foun ba {alvo.naran_kompletu} rai ona.',
            'sesaun_taka': sesaun,
            'profesor': self.get_serializer(alvo).data,
        })

    def destroy(self, request, *args, **kwargs):
        """
        Remove a teacher and, by CASCADE, every sheet, day and punch they ever
        made. Irreversible -- the dashboard asks for the password twice and
        warns before it gets here.

        An ADMIN account is refused outright: the roster now lists admins, so
        the old "invisible, therefore safe" protection is gone.
        """
        alvo = self.get_object()

        payload = ProfesorHasaiSerializer(data=request.data)
        if not payload.is_valid():
            return Response(
                {
                    'detail': 'Presiza hatama password atu konfirma.',
                    'code': 'password_presiza',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Deleting yourself would lock the school out of its own dashboard.
        if alvo.pk == request.user.pk:
            return Response(
                {'detail': 'La bele hamos konta rasik.', 'code': 'rasik'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if self._eh_admin(alvo):
            return Response(
                {
                    'detail': 'La bele hamos konta administradór. '
                              'Muda role ba PROFESSOR uluk.',
                    'code': 'eh_admin',
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # The caller's own password, not the target's: it proves who is at the
        # keyboard, which is the point of asking at all.
        if not request.user.check_password(payload.validated_data['password']):
            return Response(
                {'detail': 'Password sala.', 'code': 'password_sala'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Collected before the delete, because afterwards there is no row left
        # to tell us which files belonged to this teacher.
        fotos = _fotos_profesor(alvo)
        identidade = f'id={alvo.pk} numeru_id={alvo.numeru_id} email={alvo.email}'

        alvo.delete()
        _hasai_fotos(fotos)

        logger.warning(
            'profesor hamos: actor=id=%s alvo=%s fotos=%s',
            request.user.pk, identidade, len(fotos),
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


def _fotos_profesor(profesor):
    """
    Every image the teacher owns -- their profile photo and the evidence photo
    of each punch -- as (storage, name) pairs so any storage backend works.
    """
    fotos = []
    # The shared placeholder is skipped: a teacher who never uploaded a photo
    # still points at FOTO_DEFAULT, and removing them must not take the file
    # every other such account depends on.
    if bele_hasai_foto(profesor.foto.name):
        fotos.append((profesor.foto.storage, profesor.foto.name))

    for marka in Marka.objects.filter(prezensa__lista__profesor=profesor).only('foto'):
        if marka.foto:
            fotos.append((marka.foto.storage, marka.foto.name))

    return fotos


def _hasai_fotos(fotos):
    """
    Delete the files whose rows have just gone. A file that cannot be removed
    is logged and skipped: the rows are already committed, and failing here
    would report a delete that did in fact happen.
    """
    for storage, name in fotos:
        try:
            storage.delete(name)
        except OSError as exc:
            logger.warning('la bele hasai foto %s: %s', name, exc)


class TrokaPasswordView(APIView):
    """
    Change your own password -- teacher or admin, whoever is signed in.

    This is the counterpart to `ProfesorViewSet.reset_password`, and the two
    differ on purpose:

    * the admin reset does **not** ask for the old password, because an admin
      resetting a teacher who forgot theirs cannot possibly know it;
    * this one **does**, because the caller is changing their own credentials
      and a borrowed, unlocked browser must not be enough to take an account.

    It is also the only route by which an ADMIN can change a password at all --
    the roster refuses `rasik` and `eh_admin` on both of its password actions.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = TrokaPasswordSerializer

    def post(self, request):
        payload = TrokaPasswordSerializer(data=request.data)
        if not payload.is_valid():
            detalle = {
                'password_la_hanesan': 'Password foun rua la hanesan.',
                'password_hanesan_tuan':
                    'Password foun tenke la hanesan ho password tuan.',
            }.get(kode_erru(payload.errors))
            if detalle:
                return Response(
                    {'detail': detalle, 'code': kode_erru(payload.errors)},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(
                {
                    'detail': 'Presiza hatama password tuan no password foun dala rua.',
                    'code': 'password_presiza',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        dadus = payload.validated_data
        user = request.user

        if not user.check_password(dadus['password_tuan']):
            return Response(
                {'detail': 'Password tuan sala.', 'code': 'password_tuan_sala'},
                status=status.HTTP_403_FORBIDDEN,
            )

        fraku = erru_password_fraku(dadus['password_foun'], user)
        if fraku:
            return fraku

        user.set_password(dadus['password_foun'])
        user.save(update_fields=['password'])

        # Every *other* session is revoked -- a password change is how someone
        # reacts to a device going missing, so the old refresh tokens must die.
        # The caller keeps working: their access token is already issued and a
        # fresh pair is returned below, so the dashboard does not bounce them
        # to the login screen mid-action.
        sesaun = taka_sesaun(user)

        par = RefreshToken.for_user(user)

        logger.warning(
            'troka password: user=id=%s numeru_id=%s sesaun_taka=%s',
            user.pk, user.numeru_id, sesaun,
        )

        return Response({
            'detail': 'Password troka ho susesu.',
            'sesaun_taka': sesaun,
            'access': str(par.access_token),
            'refresh': str(par),
        })
