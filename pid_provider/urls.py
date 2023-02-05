# urls.py
from django.urls import path
from django.conf.urls import include, re_path
from rest_framework.routers import DefaultRouter

from .views import PidProviderViewSet, ArticleXMLViewSet


router = DefaultRouter()
router.register('pid_provider', PidProviderViewSet, basename='pid_provider')
# router.register('pid_requester', PidRequesterViewSet, basename='pid_requester')
router.register('article', ArticleXMLViewSet, basename='article')


app_name = 'pid_provider'
urlpatterns = [
    re_path('^', include(router.urls)),
    # re_path(r'^pid_requester', PidRequesterViewSet),
    re_path(r'^pid_provider/(?P<filename>[^/]+)$', PidProviderViewSet),
]
