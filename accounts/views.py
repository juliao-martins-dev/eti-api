from django.utils.crypto import get_random_string
from rest_framework import mixins, status, viewsets
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import User
from .permissions import EhAdmin
from .serializers import (
    FotoSerializer,
    LoginSerializer,
    LogoutSerializer,
    ProfesorAtualizaSerializer,
    ProfesorKriaSerializer,
    ProfesorRosterSerializer,
    UserSerializer,
)


class LoginView(TokenObtainPairView):
    """POST email + password -> {access, refresh, user}."""

    serializer_class = LoginSerializer


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

    The list includes deactivated accounts, because the dashboard shows them
    with a "Dezativadu" badge and offers reactivation. There is no DELETE --
    sheets reference the account, so leaving is PATCH {"is_active": false}.
    """

    serializer_class = ProfesorRosterSerializer
    permission_classes = [IsAuthenticated, EhAdmin]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_queryset(self):
        return User.objects.filter(role=User.Role.PROFESSOR)

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

        email = data.get('email')
        if email and existente.filter(email=email).exists():
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

        body = ProfesorRosterSerializer(
            profesor, context=self.get_serializer_context()
        ).data
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
        serializer.save()

        return Response(
            ProfesorRosterSerializer(
                profesor, context=self.get_serializer_context()
            ).data
        )
