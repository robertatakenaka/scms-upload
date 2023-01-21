from . import models
from rest_framework import serializers


class XMLJournalSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.XMLJournal
        fields = (
            'title',
            'issn_electronic',
            'issn_print',
        )


class XMLIssueSerializer(serializers.ModelSerializer):
    class Meta:
        model = models.XMLIssue
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
        model = models.EncodedXMLArticle
        fields = (
            'xml_uri',
            'v2', 'aop_pid', 'v3',
            'created', 'updated',
            'synchronized',
            'journal',
            'issue',
            'is_aop',
            'article_in_issue',
        )
