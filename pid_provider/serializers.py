from . import models
from rest_framework import serializers


BASE_ARTICLE_FIELDS = [
    'v3',
    'main_doi',
    'elocation_id',
    'article_titles_texts',
    'surnames',
    'collab',
    'links',
    'partial_body',
    'versions',
]


class PidV3Serializer(serializers.ModelSerializer):
    class Meta:
        model = models.PidV3
        fields = BASE_ARTICLE_FIELDS
