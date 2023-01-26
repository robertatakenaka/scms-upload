import sys
import logging

from django.db import models
from django.utils.translation import gettext_lazy as _

from core.choices import LANGUAGE
from core.models import CommonControlField
from core.forms import CoreAdminModelForm
from collection.models import (
    NewWebSiteConfiguration,
    ClassicWebsiteConfiguration,
    FileWithLang,
    AssetFile,
    Collection,
)
from collection.choices import CURRENT
from journal.choices import JOURNAL_AVAILABILTY_STATUS
from journal.models import OfficialJournal
from issue.models import Issue
from files_storage.models import Configuration as FilesStorageConfiguration
from . import choices
from . import exceptions
from .choices import MS_IMPORTED, MS_PUBLISHED, MS_TO_IGNORE


class XMLFile(FileWithLang):
    assets_files = models.ManyToManyField(AssetFile)

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

class BodyAndBackXMLFile(XMLFile):
    selected = models.BooleanField(default=False)
    version = models.IntegerField(_("Version"), null=True, blank=True)

    def __str__(self):
        return f"{super()} {self.version} {self.selected}"


class SciELOHTMLFile(FileWithLang):
    part = models.CharField(
        _('Part'), max_length=6, null=False, blank=False)
    assets_files = models.ManyToManyField(AssetFile)

    @property
    def text(self):
        try:
            response = requests.get(self.uri, timeout=10)
        except Exception as e:
            return "Unable to get text from {}".format(self.uri)
        else:
            return response.content

    def __str__(self):
        return f"{super()} {self.part}"

    class Meta:

        indexes = [
            models.Index(fields=['part']),
        ]


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
        FilesStorageConfiguration,
        verbose_name=_('Public Files Storage Configuration'),
        related_name='public_files_storage_config',
        null=True, blank=True,
        on_delete=models.SET_NULL)
    migration_files_storage_config = models.ForeignKey(
        FilesStorageConfiguration,
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
    action_name = models.CharField(
        _('Action'), max_length=255, null=True, blank=True)
    message = models.CharField(
        _('Message'), max_length=255, null=True, blank=True)
    exception_type = models.CharField(
        _('Exception Type'), max_length=255, null=True, blank=True)
    exception_msg = models.CharField(
        _('Exception Msg'), max_length=555, null=True, blank=True)
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
    isis_updated_date = models.CharField(
        _('ISIS updated date'), max_length=8, null=True, blank=True)
    isis_created_date = models.CharField(
        _('ISIS created date'), max_length=8, null=True, blank=True)

    # dados migrados
    data = models.JSONField(blank=True, null=True)

    # status da migração
    status = models.CharField(
        _('Status'), max_length=20,
        choices=choices.MIGRATION_STATUS,
        default=choices.MS_TO_MIGRATE,
    )
    failures = models.ManyToManyField(MigrationFailure)

    class Meta:
        indexes = [
            models.Index(fields=['isis_updated_date']),
            models.Index(fields=['status']),
        ]


class MigratedJournal(MigratedData):
    """
    Class that represents journals data in a SciELO Collection context
    Its attributes are related to the journal in collection
    For official data, use Journal model
    """
    collection = models.ForeignKey(Collection, on_delete=models.SET_NULL, null=True, blank=True)
    scielo_issn = models.CharField(_('SciELO ISSN'), max_length=9, null=False, blank=False)
    acron = models.CharField(_('Acronym'), max_length=25, null=True, blank=True)
    title = models.CharField(_('Title'), max_length=255, null=True, blank=True)
    availability_status = models.CharField(
        _('Availability Status'), max_length=10, null=True, blank=True,
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

    issue_pid = models.CharField(_('Issue PID'), max_length=23, null=False, blank=False)
    # v30n1 ou 2019nahead
    issue_folder = models.CharField(_('Issue Folder'), max_length=23, null=False, blank=False)

    htmls = models.ManyToManyField(SciELOHTMLFile)
    xmls = models.ManyToManyField(XMLFile)
    pdfs = models.ManyToManyField(FileWithLang, related_name='pdfs')
    assets = models.ManyToManyField(AssetFile)
    files_status = models.CharField(
        _('Status'), max_length=20,
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
            logging.info("Get or create SciELOIssue {} {} {}".format(migrated_journal, issue_pid, issue_folder))
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
            "asset": AssetFile,
            "pdf": FileWithLang,
            "xml": XMLFile,
            "html": SciELOHTMLFile,
        }

    def add_file(self, item, push_file, subdirs, preserve_name, creator):
        item_type = item.pop('type')
        ClassFile = self.ClassFileModels[item_type]
        obj = ClassFile.create_or_update(
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
        return obj

    def get_files(self, item_type, pkg_name=None, **kwargs):
        if item_type == "asset":
            files = self.assets
        elif item_type == "pdf":
            files = self.pdfs
        elif item_type == "xml":
            files = self.xmls
        elif item_type == "html":
            files = self.htmls
        if pkg_name:
            return files.filter(pkg_name=pkg_name, **kwargs)
        return files

    def add_files(self, classic_issue_files=None, get_files_storage=None,
                  creator=None,
                  ):
        result = {"failures": [], "success": []}

        preserve_name = True
        subdirs = os.path.join(
            self.migrated_journal.acron,
            self.issue_folder,
        )

        for item in classic_issue_files:
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
        return result

    @property
    def assets_uris(self):
        if not hasattr(self, '_assets_uris') or not self._assets_uris:
            self._assets_uris = {
                name: asset.uri
                for name, asset in self.assets_dict.items()
            }
        return self._assets_uris

    @property
    def assets_dict(self):
        if not hasattr(self, '_assets_as_dict') or not self._assets_as_dict:
            self._assets_as_dict = {
                asset.name: asset
                for asset in self.assets.iterator()
            }
        return self._assets_as_dict

    def update(self, classic_issue, official_issue, issue_data, force_update):
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


class MigratedDocument(MigratedData):

    migrated_issue = models.ForeignKey(MigratedIssue, on_delete=models.SET_NULL, null=True, blank=True)
    pid = models.CharField(_('PID'), max_length=23, null=True, blank=True)
    # filename without extension
    key = models.CharField(_('File key'), max_length=50, null=True, blank=True)
    main_lang = models.CharField(_("Language"), max_length=5, choices=LANGUAGE, null=True, blank=True)

    xml_files = models.ManyToManyField(XMLFile)
    rendition_files = models.ManyToManyField(FileWithLang, related_name='article_pdfs')
    html_files = models.ManyToManyField(SciELOHTMLFile, related_name='html_files')
    xml_body_files = models.ManyToManyField(BodyAndBackXMLFile, related_name='xml_body_files')
    files_status = models.CharField(
        _('Status'), max_length=20,
        choices=choices.MIGRATION_STATUS,
        default=choices.MS_TO_MIGRATE,
    )

    def __str__(self):
        return f"{self.migrated_issue} {self.key} data: {self.status} | files: {self.files_status}"

    def __unicode__(self):
        return u'%s %s' % (self.migrated_issue, self.key)

    def __str__(self):
        return u'%s %s' % (self.migrated_issue, self.key)

    class Meta:
        indexes = [
            models.Index(fields=['migrated_issue']),
            models.Index(fields=['pid']),
            models.Index(fields=['key']),
            models.Index(fields=['main_lang']),
            models.Index(fields=['files_status']),
        ]

    @classmethod
    def get_or_create(cls, pid, key, migrated_issue, creator=None):
        try:
            return cls.objects.get(
                migrated_issue=migrated_issue,
                pid=pid,
                key=key,
            )
        except cls.DoesNotExist:
            item = cls()
            item.creator = creator
            item.migrated_issue = migrated_issue
            item.pid = pid
            item.key = key
            item.save()
            return item
        except Exception as e:
            raise exceptions.GetOrCreateMigratedDocumentError(
                _('Unable to get_or_create_document_migration {} {} {}').format(
                    scielo_document, type(e), e
                )
            )

    def add_files(cls, classic_website_document, original_language,
                  migration_fs_manager, updated_by,
                  ):
        try:
            self.main_lang = original_language
            self.updated_by = updated_by
            self.set_pdf_files()
            self.set_html_files()
            self.set_xml_body_files(
                classic_website_document, migration_fs_manager, updated_by)
            self.set_xml_files(updated_by)
            # salva os dados
            self.save()

            logging.info("Add files {}".format(self))
            return self
        except Exception as e:
            raise exceptions.GetOrCreateScieloDocumentError(
                _('Unable to get_or_create_migrated_document {} {} {} {}').format(
                    migrated_issue, pid, type(e), e
                )
            )

    def add_data(self, classic_website_document, document_data, force_update):
        if self.isis_updated_date == classic_website_document.isis_updated_date:
            if not force_update:
                # nao precisa atualizar
                return
        self.isis_created_date = classic_website_document.isis_created_date
        self.isis_updated_date = classic_website_document.isis_updated_date
        self.status = MS_IMPORTED
        self.data = document_data
        self.save()

    @property
    def xml_with_pre(self):
        """
        XML with pre, remote assets
        """
        if not hasattr(self, '_xml_with_pre'):
            for xml_file in self.xml_files.iterator():
                self._xml_with_pre = (
                    xml_file.get_xml_with_pre_with_remote_assets(
                        self.migrated_issue.assets_uris)
                )
                break
        return self._xml_with_pre

    @property
    def html_texts(self):
        langs = {}
        for html_file in self.html_files.iterator():
            langs.setdefault(html_file.lang, {})
            part = f"{html_file.part} references"
            langs[html_file.lang][part] = html_file.text
        return langs

    def set_pdf_files(self):
        try:
            pdfs = self.migrated_issue.get_files('pdf', lang='main')
            pdfs[0].lang = self.main_lang
            pdfs[0].save()
        except IndexError:
            pass
        self.pdf_files.set(self.migrated_issue.get_files('pdf'))
        self.save()

    def set_html_files(self):
        self.html_files.set(self.migrated_issue.get_files("html"))
        if not self.html_files.count():
            return

    def set_xml_files(self, user):
        self.xml_files = self.migrated_issue.get_files('xml')

        if self.xml_files.count() == 0:
            subdirs = self.migrated_issue.subdirs

            selected = None
            for xml_body_file in self.xml_body_files:
                selected = xml_body_file
                if xml_body_file.selected:
                    break
            # gera xml a partir dos metadados da base isis + body + back
            xml_content = document.generate_full_xml(
                selected and selected.tostring())

            # obtém os dados para registrar o arquivo XML
            xml_file = XMLFile()
            migration_fs_manager.push_xml_content(
                xml_file, self.key + ".xml", subdirs, xml_content, user)
            self.xml_files.add(xml_file)

        for xml_file in self.xml_files.iterator():
            xml_file.set_langs()
            xml_file.save()
        self.save()

    def set_xml_body_files(self, document, migration_fs_manager, user):
        subdirs = self.migrated_issue.subdirs

        # armazena os xmls gerados a cada etapa de conversão do html
        for i, xml in enumerate(document.generate_body_and_back_from_html(self.html_texts)):
            xml_body_file = BodyAndBackXMLFile()
            xml_body_file.version = i + 1
            migration_fs_manager.push_xml_content(
                xml_body_file,
                self.key + f".{i}.xml",
                os.path.join("xml_body", subdirs),
                xml, user)
