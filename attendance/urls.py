from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import KonfigView, ListaPrezensaViewSet, PrezensaViewSet

router = DefaultRouter()
router.register('prezensa', PrezensaViewSet, basename='prezensa')
router.register('lista-prezensa', ListaPrezensaViewSet, basename='lista-prezensa')

urlpatterns = [
    path('konfig/', KonfigView.as_view(), name='konfig'),
] + router.urls
