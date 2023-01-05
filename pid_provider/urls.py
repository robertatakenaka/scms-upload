# urls.py
from django.conf.urls import include, re_path
from rest_framework.routers import DefaultRouter
from .views import PidV3ViewSet


router = DefaultRouter()
router.register('pidv3', PidV3ViewSet, basename='pidv3')

app_name = 'pid_provider'
urlpatterns = [
    re_path('^', include(router.urls)),
]
