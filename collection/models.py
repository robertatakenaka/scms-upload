import logging
from datetime import datetime
from copy import deepcopy

import requests
from django.db import models
from django.utils.translation import gettext_lazy as _
from packtools.sps.models.article_renditions import ArticleRenditions
from packtools.sps.models.related_articles import RelatedItems
from packtools.sps.models.article_assets import (
    ArticleAssets,
    SupplementaryMaterials,
)
from packtools.sps.models.article_ids import ArticleIds

from core.choices import LANGUAGE
from core.models import CommonControlField, Language
from core.forms import CoreAdminModelForm
from journal.models import OfficialJournal
from issue.models import Issue
from article.models import Article
from .choices import JOURNAL_AVAILABILTY_STATUS, WEBSITE_KIND
from . import exceptions
from files_storage.models import MinioFile
from files_storage.utils import generate_finger_print


class Collection(CommonControlField):
    """
    Class that represent the Collection
    """

    class Meta:
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['acron']),
        ]

    def __unicode__(self):
        return u'%s %s' % (self.name, self.acron)

    def __str__(self):
        return u'%s %s' % (self.name, self.acron)

    acron = models.CharField(_('Collection Acronym'), max_length=255, null=True, blank=True)
    name = models.CharField(_('Collection Name'), max_length=255, null=True, blank=True)

    base_form_class = CoreAdminModelForm

    @classmethod
    def get_or_create(cls, acron, creator, name=None):
        try:
            return cls.objects.get(acron=acron)
        except cls.DoesNotExist:
            collection = cls()
            collection.acron = acron
            collection.name = name
            collection.creator = creator
            collection.save()
            return collection
        except Exception as e:
            raise exceptions.GetOrCreateCollectionError(
                _('Unable to get_or_create_collection {} {} {}').format(
                    acron, type(e), e
                )
            )


class SciELOFile(CommonControlField):
    pkg_name = models.CharField(_('Package name'), max_length=65, null=True, blank=True)
    relative_path = models.CharField(_('Relative Path'), max_length=255, null=True, blank=True)
    remote_file = models.ForeignKey(MinioFile, null=True, blank=True, on_delete=models.SET_NULL)
    langs = models.ManyToManyField(Language)

    class Meta:
        indexes = [
            models.Index(fields=['pkg_name']),
            models.Index(fields=['relative_path']),
            models.Index(fields=['remote_file']),
        ]

    @property
    def name(self):
        return (
            self.remote_file and self.remote_file.basename or
            os.path.basename(self.relative_path))

    @property
    def uri(self):
        if self.remote_file:
            return self.remote_file.uri

    def __str__(self):
        return self.relative_path or str(self.remote_file)

    @classmethod
    def get_or_create(cls, item, creator):
        try:
            return cls.objects.get(relative_path=item['relative_path'])
        except cls.DoesNotExist:
            file = cls()
            file.pkg_name = item['key']
            file.relative_path = item.get('relative_path')
            file.creator = creator
            file.save()
            return file

    @classmethod
    def create_or_update(cls, item, push_file, subdirs, preserve_name, creator):
        obj = cls.get_or_create(item)

        response = push_file(
            obj,
            item['path'],
            subdirs,
            preserve_name,
            creator,
        )
        for k in item.keys():
            if hasattr(obj, k):
                setattr(obj, k, getattr(obj, k) or item[k])
        return obj


class FileWithLang(SciELOFile):

    lang = models.ForeignKey(Language, null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return f"{super()} {self.lang}"

    class Meta:
        indexes = [
            models.Index(fields=['lang']),
        ]


class AssetFile(SciELOFile):
    is_supplementary_material = models.BooleanField(default=False)

    def __str__(self):
        return f"{super()} {self.is_supplementary_material}"

    class Meta:
        indexes = [
            models.Index(fields=['is_supplementary_material']),
        ]


class NewWebSiteConfiguration(CommonControlField):
    url = models.CharField(
        _('New website url'), max_length=255, null=True, blank=True)
    db_uri = models.CharField(
        _('Mongodb Info'), max_length=255, null=True, blank=True,
        help_text=_('mongodb://login:password@host:port/database'))

    def __str__(self):
        return f"{self.url}"

    @classmethod
    def get_or_create(cls, url, db_uri=None, creator=None):
        try:
            return cls.objects.get(url=url)
        except cls.DoesNotExist:
            new_website_config = cls()
            new_website_config.db_uri = db_uri
            new_website_config.url = url
            new_website_config.creator = creator
            new_website_config.save()
            return new_website_config

    class Meta:
        indexes = [
            models.Index(fields=['url']),
        ]

    base_form_class = CoreAdminModelForm


class ClassicWebsiteConfiguration(CommonControlField):

    collection = models.ForeignKey(Collection, on_delete=models.SET_NULL, null=True, blank=True)

    title_path = models.CharField(
        _('Title path'), max_length=255, null=True, blank=True,
        help_text=_('Title path: title.id path or title.mst path without extension'))
    issue_path = models.CharField(
        _('Issue path'), max_length=255, null=True, blank=True,
        help_text=_('Issue path: issue.id path or issue.mst path without extension'))
    serial_path = models.CharField(
        _('Serial path'), max_length=255, null=True, blank=True,
        help_text=_('Serial path'))
    cisis_path = models.CharField(
        _('Cisis path'), max_length=255, null=True, blank=True,
        help_text=_('Cisis path where there are CISIS utilities such as mx and i2id'))
    bases_work_path = models.CharField(
        _('Bases work path'), max_length=255, null=True, blank=True,
        help_text=_('Bases work path'))
    bases_pdf_path = models.CharField(
        _('Bases pdf path'), max_length=255, null=True, blank=True,
        help_text=_('Bases translation path'))
    bases_translation_path = models.CharField(
        _('Bases translation path'), max_length=255, null=True, blank=True,
        help_text=_('Bases translation path'))
    bases_xml_path = models.CharField(
        _('Bases XML path'), max_length=255, null=True, blank=True,
        help_text=_('Bases XML path'))
    htdocs_img_revistas_path = models.CharField(
        _('Htdocs img revistas path'), max_length=255, null=True, blank=True,
        help_text=_('Htdocs img revistas path'))

    def __str__(self):
        return f"{self.collection}"

    @classmethod
    def get_or_create(cls, collection, config, user):
        try:
            return cls.objects.get(collection=collection)
        except cls.DoesNotExist:
            classic_website = cls()
            classic_website.collection = collection
            classic_website.title_path = config['title_path']
            classic_website.issue_path = config['issue_path']
            classic_website.serial_path = config['SERIAL_PATH']
            classic_website.cisis_path = config.get('CISIS_PATH')
            classic_website.bases_work_path = config['BASES_WORK_PATH']
            classic_website.bases_pdf_path = config['BASES_PDF_PATH']
            classic_website.bases_translation_path = (
                config['BASES_TRANSLATION_PATH']
            )
            classic_website.bases_xml_path = (
                config['BASES_XML_PATH']
            )
            classic_website.htdocs_img_revistas_path = (
                config['HTDOCS_IMG_REVISTAS_PATH']
            )
            classic_website.creator = user
            classic_website.save()
            return classic_website

    class Meta:
        indexes = [
            models.Index(fields=['collection']),
        ]

    base_form_class = CoreAdminModelForm
