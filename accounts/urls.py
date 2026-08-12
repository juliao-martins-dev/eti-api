from django.urls import path
from rest_framework.routers import SimpleRouter
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from .views import (
    LoginView,
    LogoutView,
    MeView,
    ProfesorViewSet,
    TrokaPasswordView,
)

urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('verify/', TokenVerifyView.as_view(), name='token_verify'),
    path('me/', MeView.as_view(), name='me'),
    path(
        'troka-password/',
        TrokaPasswordView.as_view(),
        name='troka-password',
    ),
]

# The roster is identity data but not an auth route -- core.urls mounts these
# at /api/, giving /api/profesor/.
router = SimpleRouter()
router.register('profesor', ProfesorViewSet, basename='profesor')
profesor_urlpatterns = router.urls
