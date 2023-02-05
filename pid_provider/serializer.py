from xmlsps.models import XMLJournal, XMLIssue, XMLDocPid
from rest_framework import serializers


class XMLJournalSerializer(serializers.ModelSerializer):
    class Meta:
        model = XMLJournal
        fields = (
            'title',
            'issn_electronic',
            'issn_print',
        )


class XMLIssueSerializer(serializers.ModelSerializer):
    class Meta:
        model = XMLIssue
        fields = (
            'volume',
            'number',
            'suppl',
            'pub_year',
        )


class XMLArticleSerializer(serializers.ModelSerializer):
    journal = XMLJournalSerializer()
    issue = XMLIssueSerializer()

    class Meta:
        model = XMLDocPid
        fields = (
            'xml_uri',
            'v2', 'aop_pid', 'v3',
            'created', 'updated',
            'synchronized',
            'journal',
            'issue',
            'is_aop',
        )
