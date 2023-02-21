import os
import traceback
import sys
import logging
from datetime import datetime

from django.db import models
from django.utils.translation import gettext_lazy as _
from packtools.sps.models.article_assets import (
    ArticleAssets,
)

from core.choices import LANGUAGE
from core.models import CommonControlField, Language
from core.forms import CoreAdminModelForm
from collection.models import (
    NewWebSiteConfiguration,
    ClassicWebsiteConfiguration,
    Collection,
)
from collection.choices import CURRENT
from journal.choices import JOURNAL_AVAILABILTY_STATUS
from journal.models import OfficialJournal
from issue.models import Issue
from files_storage.models import (
    MinioConfiguration,
    MinioFile,
)
from xmlsps.xml_sps_lib import get_xml_with_pre_from_uri
from . import choices
from . import exceptions
from .choices import MS_IMPORTED, MS_PUBLISHED, MS_TO_IGNORE


class MigrationConfiguration(CommonControlField):

    classic_website_config = models.ForeignKey(
        ClassicWebsiteConfiguration,
        verbose_name=_('Classic website configuration'),
        null=True, blank=True,
        on_delete=models.SET_NULL)
    new_website_config = models.ForeignKey(
        NewWebSiteConfiguration,
        verbose_name=_('New website configuration'),
        null=True, blank=True,
        on_delete=models.SET_NULL)
    public_files_storage_config = models.ForeignKey(
        MinioConfiguration,
        verbose_name=_('Public Files Storage Configuration'),
        related_name='public_files_storage_config',
        null=True, blank=True,
        on_delete=models.SET_NULL)
    migration_files_storage_config = models.ForeignKey(
        MinioConfiguration,
        verbose_name=_('Migration Files Storage Configuration'),
        related_name='migration_files_storage_config',
        null=True, blank=True,
        on_delete=models.SET_NULL)

    def __str__(self):
        return f"{self.classic_website_config}"

    @classmethod
    def get_or_create(cls, classic_website, new_website_config=None,
                      public_files_storage_config=None,
                      migration_files_storage_config=None,
                      creator=None,
                      ):
        logging.info("Get or create migration configuration")
        try:
            return cls.objects.get(classic_website_config=classic_website)
        except cls.DoesNotExist:
            migration_configuration = cls()
            migration_configuration.classic_website_config = classic_website
            migration_configuration.new_website_config = new_website_config
            migration_configuration.public_files_storage_config = public_files_storage_config
            migration_configuration.migration_files_storage_config = migration_files_storage_config
            migration_configuration.creator = creator
            migration_configuration.save()
            return migration_configuration

    class Meta:
        indexes = [
            models.Index(fields=['classic_website_config']),
        ]
    base_form_class = CoreAdminModelForm


class MigrationFailure(CommonControlField):
    action_name = models.TextField(
        _('Action'), null=True, blank=True)
    message = models.TextField(
        _('Message'), null=True, blank=True)
    exception_type = models.TextField(
        _('Exception Type'), null=True, blank=True)
    exception_msg = models.TextField(
        _('Exception Msg'), null=True, blank=True)
    traceback = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['action_name']),
        ]

    @classmethod
    def create(cls, message, action_name, e, creator):
        exc_type, exc_value, exc_traceback = sys.exc_info()
        obj = cls()
        obj.action_name = action_name
        obj.message = message
        obj.exception_msg = str(e)[:555]
        obj.traceback = [
            str(item)
            for item in traceback.extract_tb(exc_traceback)
        ]
        obj.exception_type = str(type(e))
        obj.creator = creator
        obj.save()
        return obj


class MigratedData(CommonControlField):

    # datas no registro da base isis para identificar
    # se houve mudança nos dados durante a migração
    isis_updated_date = models.TextField(
        _('ISIS updated date'), max_length=8, null=True, blank=True)
    isis_created_date = models.TextField(
        _('ISIS created date'), max_length=8, null=True, blank=True)

    # dados migrados
    data = models.JSONField(blank=True, null=True)

    # status da migração
    status = models.TextField(
        _('Status'),
        choices=choices.MIGRATION_STATUS,
        default=choices.MS_TO_MIGRATE,
    )
    failures = models.ManyToManyField(MigrationFailure)

    class Meta:
        indexes = [
            models.Index(fields=['isis_updated_date']),
            models.Index(fields=['status']),
        ]


class MigratedFile(MinioFile):
    # identifica os arquivos do mesmo documento
    pkg_name = models.TextField(_('Package name'), null=True, blank=True)
    relative_path = models.TextField(_('Relative Path'), null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['pkg_name']),
            models.Index(fields=['relative_path']),
        ]

    def __str__(self):
        return self.relative_path

    def __unicode__(self):
        return self.relative_path

    @classmethod
    def get_or_create(cls, item, creator):
        try:
            return cls.objects.get(relative_path=item['relative_path'])
        except cls.DoesNotExist:
            file = cls()
            logging.info(f"MigratedFile.get_or_create {item}")
            file.basename = item.get("basename")
            file.pkg_name = item.get("key") or item.get("pkg_name")
            file.relative_path = item['relative_path']
            file.creator = creator
            file.save()
            return file

    @classmethod
    def push(cls, item, push_file, subdirs, preserve_name, creator):
        logging.info(f"MigratedFile.push {item}")
        obj = cls.get_or_create(item, creator)

        response = push_file(
            item['path'],
            subdirs,
            preserve_name,
        )
        obj.basename = response["basename"]
        obj.uri = response["uri"]
        obj.save()
        logging.info(response)
        return obj


class MigratedPdfFile(MigratedFile):
    lang = models.ForeignKey(Language, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        indexes = [
            models.Index(fields=['lang']),
        ]

    @classmethod
    def get_or_create(cls, item, creator):
        logging.info(f"MigratedPdfFile.get_or_create {item}")
        obj = super().get_or_create(item, creator)
        if not obj.lang and item.get("lang"):
            obj.lang = Language.get_or_create(
                code2=item['lang'], creator=creator)
            obj.save()
        return obj


class MigratedAssetFile(MigratedFile):
    pass


class AssetInFile(CommonControlField):
    href = models.TextField(null=True, blank=True)
    asset_file = models.ForeignKey(MigratedAssetFile, null=True, blank=True, on_delete=models.SET_NULL)

    @classmethod
    def get_or_create(cls, href, creator=None):
        logging.info(f"AssetInFile.get_or_create {href}")
        try:
            return cls.objects.get(href=href)
        except cls.DoesNotExist:
            obj = cls()
            obj.href = href
            obj.creator = creator
            obj.save()
            return obj

    def set_asset_file(self, href, migrated_issue_assets):
        basename = os.path.basename(href)
        logging.info(f"origin_name={href}| basename={basename}")
        try:
            registered_asset = migrated_issue_assets.get(basename=basename)
        except MigratedAssetFile.DoesNotExist:
            try:
                registered_asset = MigratedAssetFile.objects.get(
                    relative_path=href)
            except MigratedAssetFile.DoesNotExist:
                registered_asset = None

        if registered_asset:
            self.asset_file = registered_asset
            self.save()
        return registered_asset


class MigratedXMLFile(MigratedFile):
    assets_in_xml = models.ManyToManyField(AssetInFile)

    @property
    def assets_uris(self):
        self._assets_uris = {}
        for item in self.assets_in_xml.iterator():
            if item.asset_file and item.asset_file.uri:
                self._assets_uris[item.href] = item.asset_file.uri
        return self._assets_uris

    def get_xml_with_pre_with_remote_assets(self, v2, v3, aop_pid):
        """
        XML with pre, remote assets
        """
        logging.info(f"MigratedXMLFile.get_xml_with_pre_with_remote_assets {self}")
        return self.xml_with_pre.get_xml_with_pre_with_remote_assets(
            v2=v2,
            v3=v3,
            aop_pid=aop_pid,
            assets_uris=self.assets_uris,
        )

    @property
    def xml_with_pre(self):
        """
        XML with pre, remote assets
        """
        logging.info(f"MigratedXMLFile.xml_with_pre {self}")
        if not hasattr(self, '_xml_with_pre') or not self._xml_with_pre:
            logging.info("xml_with_pre {}".format(self.uri))
            self._xml_with_pre = get_xml_with_pre_from_uri(self.uri)
        return self._xml_with_pre

    def add_assets(self, migrated_issue_assets, force_update=False):
        logging.info(f"MigratedXMLFile.add_assets {self}")
        xml_assets = ArticleAssets(self.xml_with_pre.xmltree).article_assets

        for xml_asset in xml_assets:
            asset_in_xml = AssetInFile.get_or_create(
                xml_asset.name, self.creator)
            if asset_in_xml.asset_file is None or force_update:
                asset_in_xml.set_asset_file(xml_asset.name, migrated_issue_assets)
                self.assets_in_xml.add(asset_in_xml)
                self.save()


class MigratedHTMLFile(MigratedFile):
    lang = models.ForeignKey(Language, null=True, blank=True, on_delete=models.SET_NULL)
    part = models.TextField(_('Part'), null=False, blank=False)
    replacements = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['lang']),
            models.Index(fields=['part']),
        ]

    @classmethod
    def get_or_create(cls, item, creator):
        logging.info(f"MigratedHTMLFile.get_or_create {item}")
        obj = super().get_or_create(item, creator)
        if not obj.lang and item.get("lang"):
            obj.lang = Language.get_or_create(
                code2=item['lang'], creator=creator)
            obj.part = item['part']
            obj.replacements = item['replacements']
            obj.save()
        return obj

    @property
    def text(self):
        logging.info(f"MigratedHTMLFile.text {self}")
        if not hasattr(self, '_text') or not self._text:
            try:
                response = requests.get(self.uri, timeout=10)
            except Exception as e:
                return "Unable to get text from {}".format(self.uri)
            else:
                self._text = response.content
            if self._text:
                for old, new in self.replacements.items():
                    self._text = self._text.replace(f'"{old}"', f'"{new}"')
        return self._text


class MigratedJournal(MigratedData):
    """
    Class that represents journals data in a SciELO Collection context
    Its attributes are related to the journal in collection
    For official data, use Journal model
    """
    collection = models.ForeignKey(Collection, on_delete=models.SET_NULL, null=True, blank=True)
    scielo_issn = models.TextField(_('SciELO ISSN'), max_length=9, null=False, blank=False)
    acron = models.TextField(_('Acronym'), null=True, blank=True)
    title = models.TextField(_('Title'), null=True, blank=True)
    availability_status = models.TextField(
        _('Availability Status'), null=True, blank=True,
        choices=JOURNAL_AVAILABILTY_STATUS)
    official_journal = models.ForeignKey(
        OfficialJournal, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        unique_together = [
            ['collection', 'scielo_issn'],
            ['collection', 'acron'],
        ]
        indexes = [
            models.Index(fields=['acron']),
            models.Index(fields=['collection']),
            models.Index(fields=['scielo_issn']),
            models.Index(fields=['availability_status']),
            models.Index(fields=['official_journal']),
        ]

    def __unicode__(self):
        return u'%s %s' % (self.collection, self.scielo_issn)

    def __str__(self):
        return f"{self.collection} {self.scielo_issn} {self.status}"

    @classmethod
    def get_or_create(cls, collection_acron, scielo_issn, creator=None):
        logging.info(f"MigratedJournal.get_or_create {collection_acron} {scielo_issn}")
        try:
            return cls.objects.get(
                collection__acron=collection_acron,
                scielo_issn=scielo_issn,
            )
        except cls.DoesNotExist:
            obj = cls()
            obj.collection = Collection.get_or_create(
                collection_acron, creator
            )
            obj.scielo_issn = scielo_issn
            obj.creator = creator
            obj.save()
            logging.info(f"Created MigratedJournal {obj}")
            return obj
        except Exception as e:
            raise exceptions.GetOrCreateMigratedJournalError(
                _('Unable to get_or_create_migrated_journal {} {} {} {}').format(
                    collection_acron, scielo_issn, type(e), e
                )
            )

    def update(
            self, updated_by, journal, force_update,
            journal_data=None,
            acron=None, title=None, availability_status=None,
            official_journal=None,
            ):
        # check if it needs to be update
        logging.info(f"MigratedJournal.update {self}")
        if self.isis_updated_date == journal.isis_updated_date:
            if not force_update:
                # nao precisa atualizar
                return
        try:
            self.official_journal = official_journal
            self.acron = acron
            self.title = title
            self.availability_status = availability_status
            self.isis_created_date = journal.isis_created_date
            self.isis_updated_date = journal.isis_updated_date
            self.status = MS_IMPORTED
            if journal.current_status != CURRENT:
                self.status = MS_TO_IGNORE
            self.data = journal_data
            self.updated_by = updated_by
            self.updated = datetime.utcnow()
            self.save()
        except Exception as e:
            raise exceptions.UpdateMigratedJournalError(
                _("Unable to update MigratedJournal %s %s %s") %
                (str(self), type(e), str(e))
            )


class MigratedIssue(MigratedData):
    migrated_journal = models.ForeignKey(MigratedJournal, on_delete=models.SET_NULL, null=True, blank=True)
    official_issue = models.ForeignKey(Issue, on_delete=models.SET_NULL, null=True, blank=True)

    issue_pid = models.TextField(_('Issue PID'), max_length=23, null=False, blank=False)
    # v30n1 ou 2019nahead
    issue_folder = models.TextField(_('Issue Folder'), max_length=23, null=False, blank=False)

    htmls = models.ManyToManyField(MigratedHTMLFile, related_name='issue_htmls')
    xmls = models.ManyToManyField(MigratedXMLFile, related_name='issue_xmls')
    pdfs = models.ManyToManyField(MigratedPdfFile, related_name='issue_pdfs')
    assets = models.ManyToManyField(MigratedAssetFile, related_name='issue_assets')
    files_status = models.TextField(
        _('Status'),
        choices=choices.MIGRATION_STATUS,
        default=choices.MS_TO_MIGRATE,
    )
    files = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['migrated_journal']),
            models.Index(fields=['official_issue']),
            models.Index(fields=['issue_pid']),
            models.Index(fields=['issue_folder']),
            models.Index(fields=['files_status']),
        ]

    def __unicode__(self):
        return f"{self.migrated_journal} {self.issue_folder} data: {self.status} | files: {self.files_status}"

    def __str__(self):
        return f"{self.migrated_journal} {self.issue_folder} data: {self.status} | files: {self.files_status}"

    @classmethod
    def get_or_create(cls, migrated_journal, issue_pid, issue_folder, creator=None):
        logging.info(f"MigratedIssue.get_or_create {migrated_journal} {issue_folder}")
        try:
            return cls.objects.get(
                migrated_journal=migrated_journal,
                issue_pid=issue_pid,
                issue_folder=issue_folder,
            )
        except cls.DoesNotExist:
            obj = cls()
            obj.migrated_journal = migrated_journal
            obj.issue_folder = issue_folder
            obj.issue_pid = issue_pid
            obj.creator = creator
            obj.save()
            logging.info(f"Created {obj}")
            return obj
        except Exception as e:
            raise exceptions.GetOrCreateMigratedIssueError(
                _('Unable to get_or_create_migrated_issue {} {} {} {}').format(
                    migrated_journal, issue_pid, type(e), e
                )
            )

    @property
    def subdirs(self):
        return f"{self.migrated_journal.acron}/{self.issue_folder}"

    @property
    def ClassFileModels(self):
        return {
            "asset": MigratedAssetFile,
            "pdf": MigratedPdfFile,
            "xml": MigratedXMLFile,
            "html": MigratedHTMLFile,
        }

    def add_file(self, item, push_file, subdirs, preserve_name, creator):
        logging.info(f"MigratedIssue.add_file {item}")
        item_type = item.pop('type')
        ClassFile = self.ClassFileModels[item_type]
        obj = ClassFile.push(
            item, push_file, subdirs, preserve_name, creator)
        if item_type == "asset":
            self.assets.add(obj)
        elif item_type == "pdf":
            self.pdfs.add(obj)
        elif item_type == "xml":
            self.xmls.add(obj)
        elif item_type == "html":
            self.htmls.add(obj)
        self.updated_by = creator
        self.save()
        logging.info(f"Added file {obj}")
        return obj

    def add_files(self, classic_issue_files=None, get_files_storage=None,
                  creator=None,
                  ):
        logging.info(f"MigratedIssue.add_files {self}")

        result = {"failures": [], "success": []}

        preserve_name = True
        subdirs = os.path.join(self.migrated_journal.acron, self.issue_folder)

        for item in classic_issue_files:
            logging.info(item)
            # instancia files storage manager (website ou migration)
            # de acordo com o arquivo
            files_storage_manager = get_files_storage(item['path'])

            try:
                file = self.add_file(
                    item,
                    files_storage_manager.push_file,
                    subdirs,
                    preserve_name,
                    creator,
                )
            except Exception as e:
                logging.exception(e)
                item['error'] = str(e)
                item['error_type'] = str(type(e))

            if item.get("error"):
                result['failures'].append(item['path'])
            else:
                result['success'].append(item['path'])

        if not result.get("failures"):
            self.files_status = MS_IMPORTED
        self.files = result
        self.save()
        logging.info(f"MigratedIssue.add_files output {result}")
        logging.info(f"MigratedIssue.add_files output {self.files_status}")
        return result

    def add_data(self, classic_issue, official_issue, issue_data, force_update):
        params = (
            self.isis_updated_date,
            classic_issue.isis_updated_date,
            force_update,
        )
        logging.info(f"MigratedIssue.add_data {params}")

        if self.isis_updated_date == classic_issue.isis_updated_date:
            if not force_update:
                # nao precisa atualizar
                return
        self.official_issue = official_issue
        self.isis_created_date = classic_issue.isis_created_date
        self.isis_updated_date = classic_issue.isis_updated_date
        self.status = MS_IMPORTED
        self.data = issue_data
        self.save()


class BodyAndBackXMLFile(MinioFile):
    selected = models.BooleanField(default=False)
    version = models.IntegerField(_("Version"), null=True, blank=True)

    def __str__(self):
        return f"{self.migrated_document} {self.version} {self.selected}"


class MigratedDocument(MigratedData):

    migrated_issue = models.ForeignKey(MigratedIssue, on_delete=models.SET_NULL, null=True, blank=True)
    v3 = models.TextField(_('PID v3'), max_length=23, null=True, blank=True)
    pid = models.TextField(_('PID v2'), max_length=23, null=True, blank=True)
    aop_pid = models.TextField(_('AOP PID'), max_length=23, null=True, blank=True)
    # filename without extension
    pkg_name = models.TextField(_('Package name'), null=True, blank=True)
    main_lang = models.ForeignKey(Language, on_delete=models.SET_NULL, null=True, blank=True)

    body_and_back_xmls = models.ManyToManyField(BodyAndBackXMLFile)
    xmls = models.ManyToManyField(MigratedXMLFile)
    pdfs = models.ManyToManyField(MigratedPdfFile)
    htmls = models.ManyToManyField(MigratedHTMLFile)
    files_status = models.TextField(
        _('Status'),
        choices=choices.MIGRATION_STATUS,
        default=choices.MS_TO_MIGRATE,
    )

    def __unicode__(self):
        return u'%s %s' % (self.migrated_issue, self.pkg_name)

    def __str__(self):
        return u'%s %s' % (self.migrated_issue, self.pkg_name)

    class Meta:
        indexes = [
            models.Index(fields=['migrated_issue']),
            models.Index(fields=['v3']),
            models.Index(fields=['pid']),
            models.Index(fields=['aop_pid']),
            models.Index(fields=['pkg_name']),
            models.Index(fields=['files_status']),
        ]

    @classmethod
    def get_or_create(cls, pid, pkg_name, migrated_issue, creator=None, aop_pid=None, v3=None):
        logging.info(f"MigratedDocument.get_or_create {migrated_issue} {pkg_name}")
        try:
            return cls.objects.get(
                migrated_issue=migrated_issue,
                pid=pid,
                pkg_name=pkg_name,
            )
        except cls.DoesNotExist:
            item = cls()
            item.creator = creator
            item.migrated_issue = migrated_issue
            item.pid = pid
            item.aop_pid = aop_pid
            item.pkg_name = pkg_name
            item.v3 = v3
            item.save()
            return item

    def add_data(self, classic_website_document, document_data, force_update, updated_by):
        logging.info(f"MigratedDocument.add_data {self}")
        if self.isis_updated_date == classic_website_document.isis_updated_date:
            if not force_update:
                # nao precisa atualizar
                return
        self.isis_created_date = classic_website_document.isis_created_date
        self.isis_updated_date = classic_website_document.isis_updated_date
        self.data = document_data
        self.updated_by = updated_by
        self.updated = datetime.utcnow()
        self.main_lang = Language.get_or_create(
            code2=classic_website_document.original_language,
            creator=updated_by)
        self.save()

    def finish(self, updated_by):
        logging.info(f"MigratedDocument.finish {self}")
        self.status = MS_IMPORTED
        self.files_status = MS_IMPORTED
        self.updated_by = updated_by
        self.updated = datetime.utcnow()
        self.save()

    @property
    def xml_with_pre(self):
        """
        XML with pre, remote assets
        """
        logging.info(f"MigratedDocument.xml_with_pre {self}")
        if not hasattr(self, '_xml_with_pre_with_remote_assets') or not self._xml_with_pre_with_remote_assets:
            self._xml_with_pre_with_remote_assets = None
            for xml_file in self.xmls.iterator():
                try:
                    self._xml_with_pre_with_remote_assets = (
                        xml_file.get_xml_with_pre_with_remote_assets(
                            v2=self.pid,
                            v3=self.v3,
                            aop_pid=self.aop_pid,
                        )
                    )
                except Exception as e:
                    raise exceptions.MigratedDocumentXmlWithPreError(
                        f"Unable to get xml_with_pre {self} {type(e)} {e}"
                    )
                break
        return self._xml_with_pre_with_remote_assets

    def add_pdfs(self, force_update):
        logging.info(f"MigratedDocument.add_pdfs {self}")
        if force_update or not self.pdfs or self.pdfs.count() == 0:
            pdfs = self.migrated_issue.pdfs.filter(pkg_name=self.pkg_name)
            for pdf in pdfs:
                if pdf.lang is None:
                    pdf.lang = Language.get_or_create(
                        code2=self.main_lang,
                        creator=self.creator)
                    pdf.save()
                self.pdfs.add(pdf)
            self.save()

    def add_migrated_xmls(self, force_update):
        logging.info(f"MigratedDocument.add_migrated_xmls {self}")
        if force_update or not self.xmls or self.xmls.count() == 0:
            # obtém os arquivos XML (originais) do fascículo
            for xml in self.migrated_issue.xmls.filter(pkg_name=self.pkg_name):
                xml.add_assets(self.migrated_issue.assets, force_update)
                self.xmls.add(xml)
            self.save()

    def add_htmls(self, force_update):
        logging.info(f"MigratedDocument.add_htmls {self}")
        if force_update or not self.htmls or self.htmls.count() == 0:
            for html in self.migrated_issue.htmls.filter(pkg_name=self.pkg_name):
                logging.info("html=%s" % html)
                self.htmls.add(html)
            self.save()

    @property
    def html_texts(self):
        if not hasattr(self, '_html_texts') or not self._html_texts:
            self._html_texts = {}
            for html_file in self.htmls.iterator():
                lang = html_file.lang.code2
                self._html_texts.setdefault(lang, {})
                part = f"{html_file.part} references"
                self._html_texts[lang][part] = html_file.text
        logging.info(f"html_texts={self._html_texts}")
        return self._html_texts

    def add_generated_xmls(self, document, migration_fs_manager, user, force_update):
        """
        Obtém os trechos que correspondem aos elementos body e back do XML
        a partir dos registros de parágrafos e dos arquivos HTML,
        converte os elementos HTML nos elementos de XML,
        monta versões de XML contendo apenas article/body, article/back,
        article/sub-article/body, article/sub-article/back.
        Armazena as versões geradas no minio e registra na base de dados
        """
        logging.info(f"MigratedDocument.add_generated_xmls {self}")
        if not self.html_texts:
            return

        try:
            if force_update or not document.xml_body_and_back:
                document.generate_body_and_back_from_html(self.html_texts)

            xml_body_and_back = None
            if force_update or not document.xml_body_and_back:
                for i, xml_body_and_back in enumerate(document.xml_body_and_back):
                    self.add_body_and_back_xml(
                        xml_body_and_back, i+1, migration_fs_manager, user)

            if force_update or not self.body_and_back_xmls or self.body_and_back_xmls.count() == 0:
                xml_body_and_back = xml_body_and_back or self.xml_body_and_back
                if xml_body_and_back:
                    xml_content = document.generate_full_xml(xml_body_and_back)
                    self._register_xml_generated_from_html(
                        xml_content, migration_fs_manager, user)
        except Exception as e:
            raise exceptions.AddGeneratedXmlsError(
                f"Unable to generate XML from HTML {self} {type(e)} {e}"
            )

    @property
    def xml_body_and_back(self):
        logging.info(f"MigratedDocument.xml_body_and_back {self}")
        selected = (
            self.body_and_back_xmls.filter(
                migrated_document=self, selected=True).first() or
            self.body_and_back_xmls.filter(
                migrated_document=self).latest("updated"))

        if selected:
            xml_with_pre = get_xml_with_pre_from_uri(selected.uri)
            return xml_with_pre.tostring()

    def add_body_and_back_xml(self, xml_body_and_back, version,
                              migration_fs_manager, user):
        """
        Obtém os trechos que correspondem aos elementos body e back do XML
        a partir dos registros de parágrafos e dos arquivos HTML,
        converte os elementos HTML nos elementos de XML,
        monta versões de XML contendo apenas article/body, article/back,
        article/sub-article/body, article/sub-article/back.
        Armazena as versões geradas no minio e registra na base de dados
        """
        logging.info(f"MigratedDocument.add_body_and_back_xml {self}")
        subdirs = self.migrated_issue.subdirs
        try:
            body_and_back_xml_file = self.body_and_back_xmls.objects.get(
                version=version)
        except:
            body_and_back_xml_file = BodyAndBackXMLFile(
                version=version, creator=user,
            )

        try:
            response = migration_fs_manager.push_xml_content(
                f"{self.pkg_name}.xml",
                os.path.join("xml_body_and_back", subdirs, str(version)),
                xml_body_and_back,
            )
            body_and_back_xml_file.uri = response["uri"]
            body_and_back_xml_file.basename = response["basename"]
            body_and_back_xml_file.save()
            self.body_and_back_xmls.add(body_and_back_xml_file)
            self.save()

        except Exception as e:
            raise exceptions.AddBodyAndBackXMLError(
                f"Unable to register body_and_back_xml {self} {version}")

    def _register_xml_generated_from_html(self, xml_from_html,
                                migration_fs_manager, user):
        logging.info(f"MigratedDocument._register_xml_generated_from_html {self}")
        try:
            # obtém os dados para registrar o arquivo XML
            subdirs = self.migrated_issue.subdirs
            basename = self.pkg_name + ".xml"
            item = dict(
                relative_path=os.path.join(
                    "xml", self.migrated_issue.subdirs, basename),
                basename=basename,
                pkg_name=self.pkg_name,
            )
            xml_file = MigratedXMLFile.get_or_create(item, user)
            response = migration_fs_manager.push_xml_content(
                basename, subdirs, xml_from_html)
            xml_file.uri = response["uri"]
            xml_file.basename = response["basename"]
            xml_file.add_assets(self.migrated_issue.assets)
            xml_file.save()
            self.xmls.add(xml_file)
            self.save()
        except Exception as e:
            raise exceptions.RegisterXmlGeneratedFromHTMLError(
                f"Unable to push and register xml (html) {self}")
