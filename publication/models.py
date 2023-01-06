from datetime import datetime

from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import CommonControlField
from . import choices

User = get_user_model()


class PublicationArticle(CommonControlField):

    v3 = models.CharField(_('PID v3'), max_length=23, blank=True, null=True)
    xml_uri = models.CharField(_('XML URI'), max_length=256, blank=True, null=True)
    status = models.CharField(
        _('Publication status'), max_length=20,
        blank=True, null=True, choices=choices.PUBLICATION_STATUS)

    @classmethod
    def get_or_create(cls, v3, creator=None, xml_uri=None, status=None):
        try:
            return cls.objects.get(v3=v3)
        except cls.DoesNotExist:
            item = cls()
            item.v3 = v3
            item.xml_uri = item.xml_uri or xml_uri
            item.status = item.status or status
            item.creator = creator
            item.created = datetime.utcnow()
            item.save()
            return item

    @classmethod
    def create_or_update(cls, v3, creator, xml_uri=None, status=None):
        try:
            item = cls.objects.get(v3=v3)
            item.updated_by = creator
            item.updated = datetime.utcnow()
        except cls.DoesNotExist:
            item = cls()
            item.v3 = v3
            item.creator = creator
            item.created = datetime.utcnow()
        item.xml_uri = item.xml_uri or xml_uri
        item.status = item.status or status
        item.save()
        return item
