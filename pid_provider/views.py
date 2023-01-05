from rest_framework.mixins import (
    CreateModelMixin, ListModelMixin, RetrieveModelMixin, UpdateModelMixin
)
from rest_framework.viewsets import GenericViewSet

from . import models
from . import serializers


class PidV3ViewSet(GenericViewSet,  # generic view functionality
                   CreateModelMixin,  # handles POSTs
                   RetrieveModelMixin,  # handles GETs for 1 Company
                   UpdateModelMixin,  # handles PUTs and PATCHes
                   ListModelMixin):  # handles GETs for many Companies

    serializer_class = serializers.PidV3Serializer
    queryset = models.PidV3.objects.all()
