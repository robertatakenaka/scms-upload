# urls.py
from django.conf.urls import include, re_path
from rest_framework.routers import DefaultRouter
from .views import PidProviderViewSet, PidRequesterViewSet


router = DefaultRouter()
router.register('pid_provider', PidProviderViewSet, basename='pid_provider')
router.register('pid_requester', PidRequesterViewSet, basename='pid_requester')

app_name = 'pidv3'
urlpatterns = [
    re_path('^', include(router.urls)),
]
