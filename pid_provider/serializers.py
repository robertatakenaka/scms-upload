from . import models
from rest_framework import serializers


class JournalSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.XMLJournal
        fields = (
            'title',
            'issn_electronic',
            'issn_print',
        )


class IssueSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.XMLIssue
        fields = (
            'volume',
            'number',
            'suppl',
            'pub_year',
        )


class PidV3Serializer(serializers.ModelSerializer):
    journal = JournalSerializer()
    issue = IssueSerializer()

    class Meta:
        model = models.PidV3
        fields = (
            'xml_uri',
            'v2', 'aop_pid', 'v3',
            'created', 'updated',
            'synchronized',
            'journal',
            'issue',
            'is_aop',
        )
