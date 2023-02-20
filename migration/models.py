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
        logging.info(_("Get or create migration configuration"))
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
            models.Index(fields=['basename']),
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
            logging.info(item)
            file.basename = item.get("basename")
            file.pkg_name = item.get("key") or item.get("pkg_name")
            file.relative_path = item['relative_path']
            file.creator = creator
            file.save()
            return file

    @classmethod
    def push(cls, item, push_file, subdirs, preserve_name, creator):
        logging.info(item)
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
        logging.info("MigratedPdfFile.get_or_create %s" % item)
        obj = super().get_or_create(cls, item, creator)
        if not obj.lang and item.get("lang"):
            obj.lang = Language.get_or_create(
                code2=item['lang'], creator=creator)
            obj.save()
        return obj


class MigratedAssetFile(MigratedFile):
    pass


class MigratedXMLFile(MigratedFile):
    assets_files = models.ManyToManyField(MigratedAssetFile)

    @property
    def xml_with_pre_with_remote_assets(self):
        """
        XML with pre, remote assets
        """
        if not hasattr(self, '_get_xml_with_pre_with_remote_assets') or not self._get_xml_with_pre_with_remote_assets:
            logging.info("xml_with_pre {}".format(self.uri))
            self._get_xml_with_pre_with_remote_assets = (
                self.xml_with_pre.get_xml_with_pre_with_remote_assets(
                    v3=self.v3,
                    v2=self.pid,
                    aop_pid=self.aop_pid,
                    assets_uris={
                        asset_file.name: asset_file.uri
                        for asset_file in self.assets_files.iterator()
                    }
                ))
        return self._get_xml_with_pre_with_remote_assets

    @property
    def xml_with_pre(self):
        """
        XML with pre, remote assets
        """
        if not hasattr(self, '_xml_with_pre') or not self._xml_with_pre:
            logging.info("xml_with_pre {}".format(self.uri))
            self._xml_with_pre = get_xml_with_pre_from_uri(self.uri)
        return self._xml_with_pre

    def add_assets(self, issue_assets):
        xml_assets = ArticleAssets(self.xml_with_pre.xmltree).article_assets

        for xml_asset in xml_assets:
            href = os.path.basename(xml_asset.name)
            try:
                registered_asset = issue_assets.get(name=href)
            except MigratedAssetFile.DoesNotExist:
                try:
                    registered_asset = MigratedAssetFile.objects.get(
                        relative_path=xml_asset.name)
                except MigratedAssetFile.DoesNotExist:
                    # TODO not found
                    registered_asset = None
            if registered_asset:
                self.assets_files.add(registered_asset)
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
        obj = super().get_or_create(cls, item, creator)
        if not obj.lang and item.get("lang"):
            obj.lang = Language.get_or_create(
                code2=item['lang'], creator=creator)
            obj.part = item['part']
            obj.replacements = item['replacements']
            obj.save()
        return obj

    @property
    def text(self):
        if not hasattr(self, '_text') or not self._text:
            try:
                response = requests.get(self.uri, timeout=10)
            except Exception as e:
                return "Unable to get text from {}".format(self.uri)
            else:
                self._text = response.content
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
        try:
            logging.info("Create or Get MigratedJournal {} {}".format(
                collection_acron, scielo_issn))
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
            logging.info("Created MigratedJournal {}".format(obj))
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
        return f"{self.migrated_journal} {self.issue_pid} {self.issue_folder} data: {self.status} | files: {self.files_status}"

    def __str__(self):
        return f"{self.migrated_journal} {self.issue_pid} {self.issue_folder} data: {self.status} | files: {self.files_status}"

    @classmethod
    def get_or_create(cls, migrated_journal, issue_pid, issue_folder, creator=None):
        try:
            logging.info("Get or create migrated issue {} {} {}".format(migrated_journal, issue_pid, issue_folder))
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
            logging.info("Created {}".format(obj))
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
        item_type = item.pop('type')
        logging.info("MigrateIssue.add_file %s " % item)
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
        logging.info("Added file %s " % obj)
        return obj

    def get_files(self, item_type, pkg_name=None, lang=None):
        logging.info(
            "MigratedIssue.get_files %s %s %s" %
            (item_type, pkg_name, lang))
        if item_type == "asset":
            files = self.assets
        elif item_type == "pdf":
            files = self.pdfs
        elif item_type == "xml":
            files = self.xmls
        elif item_type == "html":
            files = self.htmls
        if pkg_name:
            if lang:
                return files.filter(pkg_name=pkg_name, lang__code2=lang)
            return files.filter(pkg_name=pkg_name)
        return list(files)

    def add_files(self, classic_issue_files=None, get_files_storage=None,
                  creator=None,
                  ):
        logging.info("MigratedIssue input {}".format(self))

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
        logging.info("MigratedIssue output {}".format(result))
        return result

    def update(self, classic_issue, official_issue, issue_data, force_update):
        logging.info((
            self.isis_updated_date,
            classic_issue.isis_updated_date,
            force_update,
        ))
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
    xmls = models.ManyToManyField(MigratedXMLFile, related_name='xmls')
    pdfs = models.ManyToManyField(MigratedPdfFile, related_name='pdfs')
    htmls = models.ManyToManyField(MigratedHTMLFile, related_name='htmls')
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
        try:
            logging.info("Migrated Document %s %s %s" % (pid, pkg_name, migrated_issue))
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
        except Exception as e:
            raise exceptions.GetOrCreateMigratedDocumentError(
                _('Unable to get_or_create_document_migration {} {} {} {}').format(
                    migrated_issue, pkg_name, type(e), e
                )
            )

    def add_data(self, classic_website_document, document_data, force_update, updated_by):
        if self.isis_updated_date == classic_website_document.isis_updated_date:
            if not force_update:
                # nao precisa atualizar
                return
        self.isis_created_date = classic_website_document.isis_created_date
        self.isis_updated_date = classic_website_document.isis_updated_date
        self.data = document_data
        self.updated_by = updated_by
        self.updated = datetime.utcnow()
        self.save()

    def add_files(self, original_language, updated_by):
        self.main_lang = Language.get_or_create(
                    code2=original_language,
                    creator=self.updated_by or self.creator)
        self.add_pdfs()
        self.add_htmls()
        self.add_xmls()
        self.updated_by = updated_by
        self.updated = datetime.utcnow()
        self.save()
        return self

    def add_xmls(
            self, classic_website_document, migration_fs_manager, updated_by,
            force_update,
            ):
        self._add_migrated_xmls()
        if self.xmls is None or self.xmls.count() == 0 or force_update:
            if self.htmls.count():
                self._add_generated_xmls(
                    classic_website_document, migration_fs_manager, updated_by)
        return self

    def finish(self, updated_by):
        self.status = MS_IMPORTED
        self.updated_by = updated_by
        self.updated = datetime.utcnow()
        self.save()

    @property
    def xml_with_pre_with_remote_assets(self):
        # FIXME
        """
        XML with pre, remote assets
        """
        if not hasattr(self, '_xml_with_pre_with_remote_assets') or not self._xml_with_pre_with_remote_assets:
            for xml_file in self.xmls.iterator():
                self._xml_with_pre_with_remote_assets = (
                    xml_file.xml_with_pre_with_remote_assets
                )
                break
        return self._xml_with_pre_with_remote_assets

    def add_pdfs(self):
        logging.info("MigratedDocument.add_pdfs {}".format(self))
        pdfs = self.migrated_issue.get_files('pdf', self.pkg_name)
        for pdf in pdfs:
            logging.info(pdf)
            if pdf.lang.code2 is None:
                pdf.lang = self.main_lang
                pdf.save()
            self.pdfs.add(pdf)
        self.save()

    def _add_migrated_xmls(self):
        logging.info("MigratedDocument._add_migrated_xmls {}".format(self))
        # obtém os arquivos XML (originais) do fascículo
        for xml in self.migrated_issue.get_files('xml', self.pkg_name):
            logging.info(xml)
            xml.add_assets(self.migrated_issue.assets)
            self.xmls.add(xml)
        self.save()

    def add_htmls(self):
        logging.info("MigratedDocument.add_htmls {}".format(self))
        for html in self.migrated_issue.get_files("html", self.pkg_name):
            logging.info("html=%s" % html)
            self.htmls.add(html)
        self.save()

    @property
    def html_texts(self):
        if not hasattr(self, '_html_texts') or not self._html_texts:
            self._html_texts = {}
            for html_file in self.htmls.iterator():
                lang = html_file.lang.code2
                logging.info("html_file: {} {}".format(lang, html_file.part))
                self._html_texts.setdefault(lang, {})
                part = f"{html_file.part} references"
                self._html_texts[lang][part] = html_file.text
        return self._html_texts

    def _add_generated_xmls(self, document, migration_fs_manager, user):
        """
        Obtém os trechos que correspondem aos elementos body e back do XML
        a partir dos registros de parágrafos e dos arquivos HTML,
        converte os elementos HTML nos elementos de XML,
        monta versões de XML contendo apenas article/body, article/back,
        article/sub-article/body, article/sub-article/back.
        Armazena as versões geradas no minio e registra na base de dados
        """
        logging.info("MigratedDocument.set_body_and_back_xmls {}".format(self))
        if not self.html_texts:
            return

        document.generate_body_and_back_from_html(self.html_texts)

        xml_body_and_back = None
        for i, xml_body_and_back in enumerate(document.xml_body_and_back):
            self.set_body_and_back_xml(
                xml_body_and_back, i+1, migration_fs_manager, user)

        if xml_body_and_back:
            xml_content = document.generate_full_xml(xml_body_and_back)
            self._push_and_register_xmls(
                xml_content, migration_fs_manager, user)

    @property
    def xml_body_and_back(self):
        logging.info("MigratedDocument.xml_body_and_back {}".format(self))
        selected = (
            self.body_and_back_xmls.filter(
                migrated_document=self, selected=True).first() or
            self.body_and_back_xmls.filter(
                migrated_document=self).latest("updated"))

        if selected:
            xml_with_pre = get_xml_with_pre_from_uri(selected.uri)
            return xml_with_pre.tostring()

    def set_body_and_back_xml(self, xml_body_and_back, version,
                              migration_fs_manager, user):
        """
        Obtém os trechos que correspondem aos elementos body e back do XML
        a partir dos registros de parágrafos e dos arquivos HTML,
        converte os elementos HTML nos elementos de XML,
        monta versões de XML contendo apenas article/body, article/back,
        article/sub-article/body, article/sub-article/back.
        Armazena as versões geradas no minio e registra na base de dados
        """
        logging.info("MigratedDocument.generate_body_and_back_from_html {}".format(self))
        subdirs = self.migrated_issue.subdirs
        try:

            body_and_back_xml_file = self.body_and_back_xmls.objects.get(
                version=version)
        except:
            body_and_back_xml_file = BodyAndBackXMLFile(
                version=version,
                creator=user,
            )

        try:
            response = migration_fs_manager.push_xml_content(
                f"{self.pkg_name}.{version}.xml",
                os.path.join("xml_body_and_back", subdirs),
                xml_body_and_back,
            )
            body_and_back_xml_file.uri = response["uri"]
            body_and_back_xml_file.basename = response["basename"]
            body_and_back_xml_file.save()

        except Exception as e:
            raise exceptions.SetBodyAndBackXMLError(
                _("Unable to register body_and_back_xml {} {}").format(
                    self, i)
            )

    def _push_and_register_xmls(self, xml_from_html,
                               migration_fs_manager, user):
        logging.info("MigratedDocument.push_and_register_xml_content {}".format(self))
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

            # TODO set_assets

            xml_file.save()
            self.xmls.add(xml_file)
            self.save()
        except Exception as e:
            raise exceptions.SetXmlsGeneratedFromHTMLError(
                _("Unable to set xmls generated from html {} {}").format(
                    self, i)
            )
