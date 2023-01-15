# urls.py
from django.conf.urls import include, re_path
from rest_framework.routers import DefaultRouter
from .views import PidProviderViewSet, PidRequesterViewSet, XMLViewSet


router = DefaultRouter()
router.register('pid_provider', PidProviderViewSet, basename='pid_provider')
router.register('pid_requester', PidRequesterViewSet, basename='pid_requester')
router.register('xml', XMLViewSet, basename='xml')


app_name = 'xmlsps'
urlpatterns = [
    re_path('^', include(router.urls)),
    re_path(r'^pid_provider/(?P<filename>[^/]+)$', PidProviderViewSet)
]
