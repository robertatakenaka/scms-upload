from django.db import models

from .choices import WEBSITE_KIND
from collection.models import Collection


# Create your models here.
class WebSiteConfiguration(CommonControlField):
    collection = models.ForeignKey(
        Collection, null=True, blank=True, on_delete=models.SET_NULL
    )
    url = models.CharField(_("New website url"), max_length=255, null=True, blank=True)
    db_uri = models.CharField(
        _("Mongodb Info"),
        max_length=255,
        null=True,
        blank=True,
        help_text=_("mongodb://login:password@host:port/database"),
    )
    purpose = models.CharField(
        _("Purpose"), max_length=25, choices=WEBSITE_KIND, null=True, blank=True
    )

    def __str__(self):
        return f"{self.url}"

    class Meta:
        indexes = [
            models.Index(fields=["purpose"]),
            models.Index(fields=["collection"]),
        ]

    base_form_class = CoreAdminModelForm

    @classmethod
    def get(cls, url=None, collection=None, purpose=None):
        if url:
            return cls.objects.get(url=url)
        if collection and purpose:
            return cls.objects.get(collection=collection, purpose=purpose)
        raise ValueError(
            "WebSiteConfiguration.get requires url or collection and purpose parameters"
        )

    @classmethod
    def create_or_update(cls, user, url, collection, purpose, db_uri):
        try:
            obj = cls.get(url, collection, purpose)
            obj.updated_by = user
        except cls.DoesNotExist:
            obj = cls()
            obj.creator = user

        obj.url = url or obj.url
        obj.db_uri = db_uri or obj.db_uri
        obj.collection = collection or obj.collection
        obj.purpose = purpose or obj.purpose
        obj.save()
        return obj
