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
from xmlsps.xml_sps_lib import get_xml_with_pre_from_uri
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
    langs = models.ManyToManyField(Language, on_delete=models.SET_NULL)

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

    class Meta:
        indexes = [
            models.Index(fields=['pkg_name']),
            models.Index(fields=['relative_path']),
            models.Index(fields=['remote_file']),
            models.Index(fields=['langs']),
        ]


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


class XMLFile(FileWithLang):
    assets_files = models.ManyToManyField('AssetFile')

    def __str__(self):
        return f"{super()}"

    def tostring(self):
        return self.xml_with_pre.tostring()

    @property
    def xml_with_pre(self):
        if not hasattr(self, '_xml_with_pre') or not self._xml_with_pre:
            try:
                self._xml_with_pre = get_xml_with_pre_from_uri(self.uri)
            except Exception as e:
                raise exceptions.XMLFileXMLWithPreError(
                    _("Unable to get XML with pre (XMLFile) {}: {} {}").format(
                        self.uri, type(e), e
                    )
                )
        return self._xml_with_pre

    @property
    def related_articles(self):
        if not hasattr(self, '_related_articles') or not self._related_articles:
            self._related_articles = self.xml_with_pre.related_items
        return self._related_articles

    @property
    def supplementary_materials(self):
        if not hasattr(self, '_supplementary_materials') or not self._supplementary_materials:
            supplmats = SupplementaryMaterials(self.xml_with_pre.xmltree)
            self._supplementary_materials = []
            names = [item.name for item in suppl_mats.items]
            for asset_file in self.assets_files:
                if asset_file.name in names:
                    asset_file.is_supplementary_material = True
                    asset_file.save()
                if asset_file.is_supplementary_material:
                    self._supplementary_materials.append({
                        "uri": asset_file.uri,
                        "lang": self.lang,
                        "ref_id": None,
                        "filename": asset_file.name,
                    })
        return self._supplementary_materials

    def add_assets(self, issue_assets_dict):
        """
        Atribui asset_files
        """
        try:
            # obtém os assets do XML
            article_assets = ArticleAssets(self.xml_with_pre.xmltree)
            for asset_in_xml in article_assets.article_assets:
                asset = issue_assets_dict.get(asset_in_xml.name)
                if asset:
                    # FIXME tratar asset_file nao encontrado
                    self.assets_files.add(asset)
            self.save()
        except Exception as e:
            raise exceptions.AddAssetFilesError(
                _("Unable to add assets to public XML to {} {} {})").format(
                    xml_file, type(e), e
                ))

    def get_xml_with_pre_with_remote_assets(self, issue_assets_uris):
        # FIXME assets de artigo pode estar em qq outra pasta do periódico
        # há casos em que os assets do artigo VoR está na pasta ahead
        xml_with_pre = deepcopy(self.xml_with_pre)
        article_assets = ArticleAssets(xml_with_pre.xmltree)
        article_assets.replace_names(issue_assets_uris)
        return {"xml_with_pre": xml_with_pre, "name": self.pkg_name}

    def set_langs(self):
        try:
            article = ArticleRenditions(self.xml_with_pre.xmltree)
            renditions = article.article_renditions
            self.lang = renditions[0].language
            for rendition in renditions:
                self.langs.add(
                    Language.get_or_create(code2=rendition.language)
                )
            self.save()
        except Exception as e:
            raise exceptions.AddLangsToXMLFilesError(
                _("Unable to set main lang to xml {}: {} {}").format(
                    self.uri, type(e), e
                )
            )

    @property
    def languages(self):
        return [
            {"lang": lang.code2 for lang in self.langs.iterator()}
        ]

    # FIXME
    # @property
    # def xml_files_with_lang(self):
    #     if not hasattr(self, '_xml_files_with_lang') or not self._xml_files_with_lang:
    #         self._xml_files_with_lang = {}
    #         for xml_file in self.xml_files:
    #             self._xml_files_with_lang[xml_file.lang] = xml_file
    #     return self._xml_files_with_lang

    # @property
    # def text_langs(self):
    #     if not hasattr(self, '_text_langs') or not self._text_langs:
    #         self._text_langs = [
    #             {"lang": lang}
    #             for lang in self.xml_files_with_lang.keys()
    #         ]
    #     return self._text_langs

    # @property
    # def related_items(self):
    #     if not hasattr(self, '_related_items') or not self._related_items:
    #         items = []
    #         for lang, xml_file in self.xml_files_with_lang.items():
    #             items.extend(xml_file.related_articles)
    #         self._related_items = items
    #     return self._related_items

    # @property
    # def supplementary_materials(self):
    #     if not hasattr(self, '_supplementary_materials') or not self._supplementary_materials:
    #         items = []
    #         for lang, xml_file in self.xml_files_with_lang.items():
    #             items.extend(xml_file.supplementary_materials)
    #         self._supplementary_materials = items
    #     return self._supplementary_materials



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
