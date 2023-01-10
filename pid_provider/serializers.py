from . import models
from rest_framework import serializers


class PidV3Serializer(serializers.ModelSerializer):
    class Meta:
        model = models.PidV3
        fields = ('v3', 'xml_uri', 'v2', 'aop_pid')
