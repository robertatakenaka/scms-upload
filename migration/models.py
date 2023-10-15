import csv
import json
import logging
import os
import sys
import traceback
from copy import deepcopy
from datetime import datetime
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from django.core.files.base import ContentFile
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from lxml import etree
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from wagtail.admin.panels import FieldPanel, InlinePanel, ObjectList, TabbedInterface
from wagtailautocomplete.edit_handlers import AutocompletePanel
from wagtail.models import Orderable

from collection.models import Collection, Language
from core.forms import CoreAdminModelForm
from core.models import CommonControlField, IncidentTracker
from issue.models import SciELOIssue
from journal.models import SciELOJournal
from package import choices as package_choices
from package.models import BasicXMLFile, SPSPkg
from packtools.sps.models.v2.article_assets import ArticleAssets
from packtools.sps.pid_provider.xml_sps_lib import (
    XMLWithPre,
    generate_finger_print,
    split_processing_instruction_doctype_declaration_and_xml,
)
from scielo_classic_website import classic_ws
from scielo_classic_website.htmlbody.html_body import HTMLContent

from . import choices, exceptions


def _fromstring(xml_content):
    pref, xml = split_processing_instruction_doctype_declaration_and_xml(xml_content)
    return etree.fromstring(xml)


def now():
    return datetime.utcnow().isoformat().replace(":", "-").replace(".", "-")


class MigratedFileGetError(Exception):
    ...


class MigratedDocumentHTMLForbiddenError(Exception):
    ...


class MigrationError(Exception):
    ...


def modified_date(file_path):
    s = os.stat(file_path)
    return datetime.fromtimestamp(s.st_mtime)


def is_out_of_date(file_path, file_date):
    if not file_date:
        return True
    return file_date.isoformat() < modified_date(file_path).isoformat()


class ClassicWebsiteConfiguration(CommonControlField):
    collection = models.ForeignKey(
        Collection, on_delete=models.SET_NULL, null=True, blank=True
    )

    title_path = models.CharField(
        _("Title path"),
        max_length=255,
        null=True,
        blank=True,
        help_text=_("Title path: title.id path or title.mst path without extension"),
    )
    issue_path = models.CharField(
        _("Issue path"),
        max_length=255,
        null=True,
        blank=True,
        help_text=_("Issue path: issue.id path or issue.mst path without extension"),
    )
    serial_path = models.CharField(
        _("Serial path"),
        max_length=255,
        null=True,
        blank=True,
        help_text=_("Serial path"),
    )
    cisis_path = models.CharField(
        _("Cisis path"),
        max_length=255,
        null=True,
        blank=True,
        help_text=_("Cisis path where there are CISIS utilities such as mx and i2id"),
    )
    bases_work_path = models.CharField(
        _("Bases work path"),
        max_length=255,
        null=True,
        blank=True,
        help_text=_("Bases work path"),
    )
    bases_pdf_path = models.CharField(
        _("Bases pdf path"),
        max_length=255,
        null=True,
        blank=True,
        help_text=_("Bases translation path"),
    )
    bases_translation_path = models.CharField(
        _("Bases translation path"),
        max_length=255,
        null=True,
        blank=True,
        help_text=_("Bases translation path"),
    )
    bases_xml_path = models.CharField(
        _("Bases XML path"),
        max_length=255,
        null=True,
        blank=True,
        help_text=_("Bases XML path"),
    )
    htdocs_img_revistas_path = models.CharField(
        _("Htdocs img revistas path"),
        max_length=255,
        null=True,
        blank=True,
        help_text=_("Htdocs img revistas path"),
    )

    def __str__(self):
        return f"{self.collection}"

    class Meta:
        indexes = [
            models.Index(fields=["collection"]),
        ]

    @classmethod
    def get_or_create(
        cls,
        collection,
        user=None,
        title_path=None,
        issue_path=None,
        serial_path=None,
        cisis_path=None,
        bases_work_path=None,
        bases_pdf_path=None,
        bases_translation_path=None,
        bases_xml_path=None,
        htdocs_img_revistas_path=None,
    ):
        try:
            return cls.objects.get(collection=collection)
        except cls.DoesNotExist:
            obj = cls()
            obj.collection = collection
            obj.title_path = title_path
            obj.issue_path = issue_path
            obj.serial_path = serial_path
            obj.cisis_path = cisis_path
            obj.bases_work_path = bases_work_path
            obj.bases_pdf_path = bases_pdf_path
            obj.bases_translation_path = bases_translation_path
            obj.bases_xml_path = bases_xml_path
            obj.htdocs_img_revistas_path = htdocs_img_revistas_path
            obj.creator = user
            obj.save()
            return obj

    base_form_class = CoreAdminModelForm


class MigratedData(CommonControlField, IncidentTracker):
    collection = models.ForeignKey(
        Collection, on_delete=models.SET_NULL, null=True, blank=True
    )

    pid = models.CharField(_("PID"), max_length=23, null=True, blank=True)

    # datas no registro da base isis para identificar
    # se houve mudança nos dados durante a migração
    isis_updated_date = models.CharField(
        _("ISIS updated date"), max_length=8, null=True, blank=True
    )
    isis_created_date = models.CharField(
        _("ISIS created date"), max_length=8, null=True, blank=True
    )

    # dados migrados
    data = models.JSONField(blank=True, null=True)

    # status da migração
    status = models.CharField(
        _("Status"),
        max_length=26,
        choices=choices.MIGRATION_STATUS,
        default=choices.MS_TO_MIGRATE,
    )

    panel_status = [
        FieldPanel("status"),
    ]

    panel_migrated_data = [
        AutocompletePanel("collection"),
        FieldPanel("pid"),
        FieldPanel("isis_updated_date"),
        FieldPanel("isis_created_date"),
        FieldPanel("data"),
    ]

    # panel_migration_report = [
    #     FieldPanel("incident_report"),
    # ]

    edit_handler = TabbedInterface(
        [
            ObjectList(panel_status, heading=_("Status")),
            ObjectList(panel_migrated_data, heading=_("Migration Data")),
        ]
    )

    class Meta:
        indexes = [
            models.Index(fields=["pid"]),
            models.Index(fields=["status"]),
            models.Index(fields=["isis_updated_date"]),
        ]

    def __str__(self):
        return f"{self.collection} {self.pid}"

    @classmethod
    def get(cls, collection, pid):
        return cls.objects.get(collection=collection, pid=pid)

    @classmethod
    def create_or_update(
        cls,
        collection,
        pid,
        user=None,
        isis_created_date=None,
        isis_updated_date=None,
        data=None,
        status=None,
        force_update=None,
    ):
        try:
            obj = cls.get(collection=collection, pid=pid)

            if (
                force_update
                or not obj.isis_updated_date
                or obj.isis_updated_date < isis_updated_date
                or data != obj.data
            ):
                obj.updated_by = user
            else:
                return obj
        except cls.DoesNotExist:
            obj = cls()
            obj.collection = collection
            obj.pid = pid
            obj.creator = user
            obj.save()

        try:
            obj.isis_created_date = isis_created_date or obj.isis_created_date
            obj.isis_updated_date = isis_updated_date or obj.isis_updated_date

            if obj.isis_created_date:
                if not obj.isis_updated_date:
                    obj.isis_updated_date = now()[:10].replace("-", "")
            else:
                obj.isis_created_date = now()[:10].replace("-", "")

            obj.data = data or obj.data

            obj.save()
            return obj
        except Exception as e:
            raise exceptions.CreateOrUpdateMigratedError(
                _("Unable to create_or_update_migrated_data {} {} {} {}").format(
                    collection, pid, type(e), e
                )
            )


def migrated_files_directory_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/user_<id>/<filename>
    issue_pid = instance.migrated_issue.pid
    try:
        return (
            f"migration/{issue_pid[:9]}/"
            f"{issue_pid[9:13]}/"
            f"{issue_pid[13:]}/{instance.pkg_name}/"
            f"{filename}"
        )
    except AttributeError:
        return (
            f"migration/{issue_pid[:9]}/"
            f"{issue_pid[9:13]}/"
            f"{issue_pid[13:]}/"
            f"{filename}"
        )


class MigratedFile(CommonControlField, Orderable):
    scielo_issue = models.ForeignKey(
        SciELOIssue, on_delete=models.SET_NULL, null=True, blank=True
    )
    file = models.FileField(
        upload_to=migrated_files_directory_path, null=True, blank=True
    )
    # bases/pdf/acron/volnum/pt_a01.pdf
    original_path = models.TextField(_("Original Path"), null=True, blank=True)

    # pt_a01.pdf
    original_name = models.TextField(_("Original name"), null=True, blank=True)
    file_date = models.DateField()

    def __str__(self):
        return f"{self.scielo_issue} {self.original_path}"

    def autocomplete_label(self):
        return f"{self.scielo_issue} {self.original_path}"

    panels = [
        FieldPanel("file"),
        FieldPanel("file_date"),
        FieldPanel("original_path"),
        FieldPanel("original_name"),
    ]

    class Meta:
        indexes = [
            models.Index(fields=["original_name"]),
            models.Index(fields=["original_path"]),
        ]

    autocomplete_search_field = "original_path"

    def save_file(self, name, content):
        if self.file:
            try:
                with open(self.file.path, "rb") as fp:
                    c = fp.read()
                    if c == content:
                        return
                    else:
                        self.file.delete(save=True)
            except Exception as e:
                pass
        self.file.save(name, ContentFile(content))

    @classmethod
    def get(
        cls,
        scielo_issue,
        original_path,
    ):
        if original_path and scielo_issue:
            # bases/pdf/acron/volume/file.pdf
            return cls.objects.get(
                scielo_issue=scielo_issue,
                original_path=original_path,
            )

        raise MigratedFileGetError(
            _(
                "MigratedFile.get requires original_path or original_name or"
                " original_href or pkg_name or category and lang and part"
            )
        )

    @property
    def filename(self):
        collection_acron = self.scielo_issue.scielo_journal.collection.acron
        journal_acron = self.scielo_issue.scielo_journal.acron
        issue_folder = self.scielo_issue.issue_folder
        basename = os.path.basename(self.original_path)
        return f"{collection_acron}_{journal_acron}_{issue_folder}_{basename}"


class AssetFile(MigratedFile):
    migrated_issue = ParentalKey("MigratedIssue", related_name="asset_file")
    # /pdf/acron/volnum/pt_a01.pdf
    original_href = models.TextField(_("Original href"), null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["original_href"]),
        ]

    def autocomplete_label(self):
        return self.original_path

    @classmethod
    def get_original_href(self, original_path):
        try:
            return original_path[original_path.find("/") :]
        except:
            pass

    @classmethod
    def create_or_update(
        cls,
        migrated_issue,
        original_path=None,
        source_path=None,
        user=None,
        force_update=None,
    ):
        try:
            input_data = dict(
                scielo_issue=migrated_issue.scielo_issue,
                original_path=original_path,
            )
            obj = cls.get(**input_data)
        except cls.DoesNotExist:
            obj = cls()
            obj.creator = user
            obj.scielo_issue = migrated_issue.scielo_issue
            obj.migrated_issue = migrated_issue
            obj.original_path = original_path
            obj.original_name = original_path and os.path.basename(original_path)
            obj.original_href = cls.get_original_href(original_path)
        else:
            # já existe
            if force_update or is_out_of_date(source_path, obj.file_date):
                obj.updated_by = user
            else:
                return obj
        try:
            obj.file_date = modified_date(source_path)
            obj.save()

            # cria / atualiza arquivo
            with open(source_path, "rb") as fp:
                obj.save_file(obj.filename, fp.read())
            obj.save()
            return obj
        except Exception as e:
            raise exceptions.CreateOrUpdateMigratedFileError(
                _("Unable to get_or_create_migrated_issue_file {} {} {} {}").format(
                    migrated_issue, original_path, type(e), e
                )
            )


class Rendition(MigratedFile):
    migrated_document = ParentalKey("MigratedDocument", related_name="rendition")
    lang = models.ForeignKey(Language, null=True, blank=True, on_delete=models.SET_NULL)
    # a01
    pkg_name = models.TextField(_("Package name"), null=True, blank=True)

    # /pdf/acron/volnum/pt_a01.pdf
    original_href = models.TextField(_("Original href"), null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["original_href"]),
            models.Index(fields=["pkg_name"]),
        ]

    autocomplete_search_field = "original_path"

    @classmethod
    def get_original_href(self, original_path):
        try:
            return original_path[original_path.find("/") :]
        except:
            pass

    @classmethod
    def create_or_update(
        cls,
        migrated_document,
        original_path=None,
        source_path=None,
        user=None,
        force_update=None,
        lang=None,
        pkg_name=None,
    ):
        try:
            input_data = dict(
                scielo_issue=migrated_document.migrated_issue.scielo_issue,
                original_path=original_path,
            )
            obj = cls.get(**input_data)
        except cls.DoesNotExist:
            obj = cls()
            obj.creator = user
            obj.scielo_issue = migrated_document.migrated_issue.scielo_issue
            obj.migrated_document = migrated_document
            obj.original_path = original_path
            obj.original_name = original_path and os.path.basename(original_path)
            obj.original_href = cls.get_original_href(original_path)
        else:
            # já existe
            if force_update or is_out_of_date(source_path, obj.file_date):
                obj.updated_by = user
            else:
                return obj
        try:
            obj.file_date = modified_date(source_path)
            if lang:
                obj.lang = Language.get_or_create(code2=lang, creator=user)
            obj.pkg_name = pkg_name
            obj.save()

            # cria / atualiza arquivo
            with open(source_path, "rb") as fp:
                obj.save_file(obj.filename, fp.read())
            obj.save()
            return obj
        except Exception as e:
            raise exceptions.CreateOrUpdateMigratedFileError(
                _("Unable to get_or_create_migrated_issue_file {} {} {} {}").format(
                    migrated_issue, original_path, type(e), e
                )
            )


class TranslationFile(MigratedFile):
    migrated_document_html = ParentalKey(
        "MigratedDocumentHTML", related_name="translation_file"
    )
    part = models.IntegerField(_("Part"), null=True, blank=True)
    lang = models.ForeignKey(Language, null=True, blank=True, on_delete=models.SET_NULL)
    # a01
    pkg_name = models.TextField(_("Package name"), null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["pkg_name"]),
        ]

    autocomplete_search_field = "original_path"

    @classmethod
    def get_original_href(self, original_path):
        try:
            return original_path[original_path.find("/") :]
        except:
            pass

    @classmethod
    def create_or_update(
        cls,
        migrated_document_html=None,
        original_path=None,
        source_path=None,
        user=None,
        force_update=None,
        lang=None,
        pkg_name=None,
        part=None,
    ):
        try:
            scielo_issue = migrated_document_html.migrated_issue.scielo_issue
            input_data = dict(
                scielo_issue=scielo_issue,
                original_path=original_path,
            )
            obj = cls.get(**input_data)
        except cls.DoesNotExist:
            obj = cls()
            obj.creator = user
            obj.migrated_document_html = migrated_document_html
            obj.scielo_issue = scielo_issue
            obj.original_path = original_path
            obj.original_name = original_path and os.path.basename(original_path)
            obj.original_href = cls.get_original_href(original_path)
        else:
            # já existe
            if force_update or is_out_of_date(source_path, obj.file_date):
                obj.updated_by = user
            else:
                return obj
        try:
            obj.file_date = modified_date(source_path)
            if lang:
                obj.lang = Language.get_or_create(code2=lang, creator=user)
            obj.pkg_name = pkg_name
            obj.part = part
            obj.save()

            # cria / atualiza arquivo
            with open(source_path, "rb") as fp:
                obj.save_file(obj.filename, fp.read())
            obj.save()
            return obj
        except Exception as e:
            raise exceptions.CreateOrUpdateMigratedFileError(
                _("Unable to get_or_create_migrated_issue_file {} {} {} {}").format(
                    scielo_issue, original_path, type(e), e
                )
            )

    @property
    def text(self):
        try:
            with open(self.file.path, mode="r", encoding="iso-8859-1") as fp:
                return fp.read()
        except:
            with open(self.file.path, mode="r", encoding="utf-8") as fp:
                return fp.read()


class MigratedJournal(MigratedData):
    """
    Dados migrados do periódico do site clássico
    """

    scielo_journal = models.ForeignKey(
        SciELOJournal, on_delete=models.SET_NULL, null=True, blank=True
    )

    def __str__(self):
        alt = f"{self.collection} {self.pid}"
        return f"{self.scielo_journal or alt}"

    def autocomplete_label(self):
        alt = f"{self.collection} {self.pid}"
        return f"{self.scielo_journal or alt}"


class MigratedIssue(MigratedData, ClusterableModel):
    scielo_issue = models.ForeignKey(
        SciELOIssue, on_delete=models.SET_NULL, null=True, blank=True
    )
    asset_files = models.ManyToManyField("AssetFile", related_name="asset_files")

    # situacao dos MigratedFile
    files_status = models.CharField(
        _("Files Status"),
        max_length=26,
        choices=choices.MIGRATION_STATUS,
        default=choices.MS_TO_MIGRATE,
    )

    # situacao dos MigratedDocument
    docs_status = models.CharField(
        _("Documents Status"),
        max_length=26,
        choices=choices.MIGRATION_STATUS,
        default=choices.MS_TO_MIGRATE,
    )

    def autocomplete_label(self):
        return str(self.scielo_issue)

    panel_status = [
        FieldPanel("status"),
        FieldPanel("files_status"),
        FieldPanel("docs_status"),
    ]

    # panel_migrated_data = [
    #     AutocompletePanel("collection"),
    #     FieldPanel("pid"),
    #     FieldPanel("isis_updated_date"),
    #     FieldPanel("isis_created_date"),
    #     FieldPanel("data"),
    # ]

    panel_assets = [
        InlinePanel("asset_file", label=_("Migrated files"), related_name="asset_file"),
    ]

    # panel_migration_report = [
    #     FieldPanel("incident_report"),
    # ]

    edit_handler = TabbedInterface(
        [
            ObjectList(panel_status, heading=_("Status")),
            ObjectList(panel_migrated_data, heading=_("Migration Data")),
            ObjectList(panel_assets, heading=_("Asset files")),
        ]
    )

    def __str__(self):
        alt = f"{self.collection} {self.pid}"
        return f"{self.scielo_issue or alt}"

    @property
    def sps_generated(self):
        status = set()
        for item in MigratedDocument.objects.filter(
            migrated_issue=self,
        ).iterator():
            status.add(item.status)
        if len(status) == 1 and status == set([choices.MS_IMPORTED]):
            return True

    def add_file(
        self,
        original_path=None,
        source_path=None,
        category=None,
        lang=None,
        part=None,
        pkg_name=None,
        user=None,
        force_update=None,
    ):
        """
        {"type": "pdf", "key": name, "path": path, "name": basename, "lang": lang}
        {"type": "xml", "key": name, "path": path, "name": basename, }
        {"type": "html", "key": name, "path": path, "name": basename, "lang": lang, "part": label}
        {"type": "asset", "path": item, "name": os.path.basename(item)}

        original_path=self._get_classic_website_rel_path(file["path"]),
        source_path=file["path"],
        category=category,
        lang=file.get("lang"),
        part=file.get("part"),
        pkg_name=file.get("key"),
        creator=self.user,
        force_update=self.force_update,

        """
        if category in ("asset", "supplmat"):
            self.save()
            return self.asset_files.add(
                AssetFile.create_or_update(
                    self,
                    original_path,
                    source_path,
                    user,
                    force_update,
                )
            )

        if category == "rendition":
            mdoc = MigratedDocument.create_or_update(
                user=user, pkg_name=pkg_name, migrated_issue=self
            )
            return mdoc.renditions.add(
                Rendition.create_or_update(
                    migrated_document=mdoc,
                    original_path=original_path,
                    source_path=source_path,
                    user=user,
                    force_update=force_update,
                    lang=lang,
                    pkg_name=pkg_name,
                )
            )
        if category == "xml":
            mdoc = MigratedDocument.create_or_update(
                user=user, pkg_name=pkg_name, migrated_issue=self
            )
            with open(source_path) as fp:
                mdoc.save_file(pkg_name + ".xml", fp.read())
            return mdoc

        if category == "html":
            logging.info(self)
            mdoc = MigratedDocumentHTML.create_or_update(
                user=user, pkg_name=pkg_name, migrated_issue=self
            )
            return mdoc.translation_files.add(
                TranslationFile.create_or_update(
                    migrated_document_html=mdoc,
                    user=user,
                    pkg_name=pkg_name,
                    lang=lang,
                    part=1 if part == "before" else 2,
                    original_path=original_path,
                    source_path=source_path,
                    force_update=force_update,
                )
            )


class MigratedDocument(MigratedData, BasicXMLFile, ClusterableModel):
    migrated_issue = models.ForeignKey(
        MigratedIssue, null=True, blank=True, on_delete=models.SET_NULL
    )
    pkg_name = models.TextField(_("Package name"), null=True, blank=True)
    sps_pkg = models.ForeignKey(
        SPSPkg, null=True, blank=True, on_delete=models.SET_NULL
    )
    missing_assets = models.JSONField(null=True, blank=True)
    file = models.FileField(
        upload_to=migrated_files_directory_path, null=True, blank=True
    )
    # status da migração
    xml_status = models.CharField(
        _("Status"),
        max_length=26,
        choices=choices.DOC_XML_STATUS,
        null=True,
        blank=True,
    )
    renditions = models.ManyToManyField(Rendition)

    panel_status = [
        FieldPanel("xml_status"),
    ]

    panel_files = [
        FieldPanel("file", label=_("XML")),
        FieldPanel("sps_pkg", label=_("SPS Package")),
        FieldPanel("missing_assets"),
    ]

    panel_renditions = [
        InlinePanel("rendition", label=_("Renditions"), related_name="rendition"),
    ]

    # panel_migration_report = [
    #     FieldPanel("incident_report"),
    # ]

    edit_handler = TabbedInterface(
        [
            ObjectList(panel_status, heading=_("Status")),
            ObjectList(panel_migrated_data, heading=_("Migration Data")),
            ObjectList(panel_renditions, heading=_("Renditions")),
            ObjectList(panel_files, heading=_("XML")),
        ]
    )

    class Meta:
        indexes = [
            models.Index(fields=["pkg_name"]),
        ]

    def __str__(self):
        return f"{self.migrated_issue} {self.pkg_name}"

    def autocomplete_label(self):
        return f"{self.migrated_issue} {self.pkg_name}"

    @classmethod
    def get(
        cls,
        collection=None,
        pid=None,
        migrated_issue=None,
        pkg_name=None,
    ):
        if collection and pid:
            return cls.objects.get(collection=collection, pid=pid)

        if pkg_name and pid and collection:
            return cls.objects.get(
                collection=collection, migrated_issue__pid=pid[1:-5], pkg_name=pkg_name
            )

        if migrated_issue and pkg_name:
            return cls.objects.get(migrated_issue=migrated_issue, pkg_name=pkg_name)
        raise ValueError(
            "MigratedDocument.get requires collection, pid, migrated_issue, pkg_name"
        )

    @classmethod
    def create_or_update(
        cls,
        collection=None,
        pid=None,
        migrated_issue=None,
        pkg_name=None,
        user=None,
        isis_created_date=None,
        isis_updated_date=None,
        data=None,
        status=None,
        sps_pkg_name=None,
        force_update=None,
    ):
        try:
            obj = cls.get(
                collection=collection,
                pid=pid,
                migrated_issue=migrated_issue,
                pkg_name=pkg_name,
            )
            if (
                force_update
                or not obj.isis_updated_date
                or obj.isis_updated_date < isis_updated_date
                or obj.data != data
            ):
                obj.updated_by = user
            else:
                return obj
        except cls.MultipleObjectsReturned as e:
            if collection and pid:
                cls.objects.filter(
                    collection=collection,
                    pid=pid,
                ).delete()

            if migrated_issue and pkg_name:
                cls.objects.filter(
                    migrated_issue=migrated_issue,
                    pkg_name=pkg_name,
                ).delete()

            obj = cls()
            obj.creator = user
        except cls.DoesNotExist:
            obj = cls()
            obj.creator = user
        try:
            if data:
                s = json.dumps(data)
                b = s.encode("iso-8859-1")
                s2 = b.decode("utf-8")
                data = json.loads(s2)
            obj.data = data or obj.data
            collection = collection or obj.collection
            collection = (
                collection or obj.migrated_issue and obj.migrated_issue.collection
            )
            obj.collection = collection
            obj.pid = pid or obj.pid
            obj.migrated_issue = migrated_issue or obj.migrated_issue
            obj.pkg_name = pkg_name or obj.pkg_name
            obj.isis_created_date = isis_created_date
            obj.isis_updated_date = isis_updated_date
            obj.status = status or obj.status
            obj.save()

            return obj
        except Exception as e:
            raise exceptions.CreateOrUpdateMigratedDocumentError(
                _("Unable to create_or_update_migrated_document {} {} {} {}").format(
                    collection, pid, type(e), e
                )
            )

    def build_sps_package(self, user, output_folder):
        """
        A partir do XML original ou gerado a partir do HTML, e
        dos ativos digitais, todos registrados em MigratedFile,
        cria o zip com nome no padrão SPS (ISSN-ACRON-VOL-NUM-SUPPL-ARTICLE) e
        o armazena em SPSPkg.not_optimised_zip_file.
        Neste momento o XML não contém pid v3.
        """
        try:
            # gera nome de pacote padrão SPS ISSN-ACRON-VOL-NUM-SUPPL-ARTICLE
            sps_pkg_name = self.sps_pkg_name
            sps_pkg_zip_path = os.path.join(output_folder, f"{sps_pkg_name}.zip")

            # cria pacote zip
            with ZipFile(sps_pkg_zip_path, "w") as zf:
                # add renditions (pdf) to zip
                self._build_sps_package_add_renditions(zf, user, sps_pkg_name)

                # A partir do XML, obtém os nomes dos arquivos dos ativos digitais
                self._build_sps_package_add_assets(zf, user, sps_pkg_name)

                # adiciona XML em zip
                self._build_sps_package_add_xml(zf, user, sps_pkg_name)

            # XML_WIP or MISSING_ASSETS or XML_WIP_AND_MISSING_ASSETS
            self.xml_status = choices.DOC_TO_GENERATE_SPS_PKG
            self.save()

            return sps_pkg_zip_path

        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            message = _("Unable to build sps package {} {}").format(
                self.collection.acron, sps_pkg_name
            )
            self.add_incident(
                collection_acron=self.collection.acron,
                app_name="migration",
                user=user,
                context="build-sps-package",
                item_name="zip",
                item_id=sps_pkg_name,
                e=e,
                message=message,
                exc_traceback=exc_traceback,
            )

    def _build_sps_package_add_renditions(self, zf, user, sps_pkg_name):
        for rendition in self.renditions.all():
            try:
                if rendition.lang:
                    sps_filename = f"{sps_pkg_name}-{rendition.lang}.pdf"
                else:
                    sps_filename = f"{sps_pkg_name}.pdf"
                zf.write(rendition.file.path, arcname=sps_filename)
            except Exception as e:
                message = _(
                    "Unable to _build_sps_package_add_renditions {} {} {}"
                ).format(self.collection.acron, sps_pkg_name, rendition)
                exc_type, exc_value, exc_traceback = sys.exc_info()
                self.add_incident(
                    collection_acron=self.collection.acron,
                    app_name="migration",
                    user=user,
                    context="build-sps-package",
                    item_name="rendition",
                    item_id=str(rendition),
                    e=e,
                    message=message,
                    exc_traceback=exc_traceback,
                )

    def _build_sps_package_add_assets(self, zf, user, sps_pkg_name):
        replacements = {}
        missing_assets = []

        # obter xml_with_pre antes de trocar os valores de xlink:href
        xml_with_pre = self.xml_with_pre

        xml_assets = ArticleAssets(xml_with_pre.xmltree)
        for xml_graphic in xml_assets.items:
            basename = os.path.basename(xml_graphic.xlink_href)
            name, ext = os.path.splitext(basename)

            found = False

            searched_by = [basename, name]
            # procura a "imagem" no contexto do "issue"
            for asset in self.migrated_issue.asset_files.filter(
                Q(original_name=basename) | Q(original_name__startswith=name + "."),
            ):
                found = True
                logging.info(
                    f"Found {xml_graphic.xlink_href} searching by {name} {basename}"
                )
                self._build_sps_package_add_asset(
                    zf, asset, xml_graphic, replacements, user
                )
            if not found:
                subdir = os.path.join(
                    self.migrated_issue.scielo_issue.scielo_journal.acron,
                    self.migrated_issue.scielo_issue.issue_folder,
                )
                path = os.path.join("/img/revistas/", subdir, xml_graphic.xlink_href)
                original_href = os.path.normpath(path)
                name, ext = os.path.splitext(original_href)

                searched_by += [original_href, name]
                # procura a "imagem" no contexto da "coleção"
                for asset in AssetFile.objects.filter(
                    Q(original_href=original_href)
                    | Q(original_href__startswith=name + "."),
                    migrated_issue__collection=self.collection,
                ):
                    found = True
                    logging.info(
                        f"Found {xml_graphic.xlink_href} searching by {original_href} {name}"
                    )
                    self._build_sps_package_add_asset(
                        zf, asset, xml_graphic, replacements, user
                    )
            if not found:
                subdir = os.path.join(
                    self.migrated_issue.scielo_issue.scielo_journal.acron,
                    self.migrated_issue.scielo_issue.issue_folder,
                    "html",
                )
                path = os.path.join("/img/revistas/", subdir, xml_graphic.xlink_href)
                original_href = os.path.normpath(path)
                name, ext = os.path.splitext(original_href)
                searched_by += [original_href, name]
                for asset in AssetFile.objects.filter(
                    Q(original_href=original_href)
                    | Q(original_href__startswith=name + "."),
                    migrated_issue__collection=self.collection,
                ):
                    found = True
                    logging.info(f"Found {xml_graphic.xlink_href} | {original_href}")
                    self._build_sps_package_add_asset(
                        zf, asset, xml_graphic, replacements, user, sps_pkg_name
                    )
            if not found:
                missing_assets.append(xml_graphic.xlink_href)
                logging.info(f"Searched by {searched_by}")

        # obter xml_filename antes de trocar os valores de xlink:href
        xml_filename = sps_pkg_name + ".xml"

        xml_assets.replace_names(replacements)
        self.missing_assets = missing_assets

        logging.info(f"missing_assets: {missing_assets}")
        self.save_file(xml_filename, xml_with_pre.tostring())
        self.save()

    def _build_sps_package_add_asset(
        self, zf, asset, xml_graphic, replacements, user, sps_pkg_name
    ):
        try:
            # obtém o nome do arquivo no padrão sps
            sps_filename = xml_graphic.name_canonical(sps_pkg_name)

            # indica a troca de href original para o padrão SPS
            replacements[xml_graphic.xlink_href] = sps_filename

            # TODO lembrar a motivacao do codigo abaixo
            # if asset.sps_pkg_name and asset.sps_pkg_name != sps_filename:
            #     # cria uma cópia
            #     obj = deepcopy(asset)
            #     obj.sps_pkg_name = sps_filename
            #     obj.save()

            # adiciona arquivo ao zip
            zf.write(asset.file.path, arcname=sps_filename)

        except Exception as e:
            message = _("Unable to _build_sps_package_add_asset {} {}").format(
                sps_pkg_name, asset.original_name
            )
            exc_type, exc_value, exc_traceback = sys.exc_info()
            self.add_incident(
                collection_acron=self.collection.acron,
                app_name="migration",
                user=user,
                context="build-sps-package",
                item_name="asset",
                item_id=asset.original_name,
                e=e,
                message=message,
                exc_traceback=exc_traceback,
            )

    def _build_sps_package_add_xml(self, zf, user, sps_pkg_name):
        try:
            sps_xml_name = sps_pkg_name + ".xml"
            zf.writestr(sps_xml_name, self.xml_with_pre.tostring())

        except Exception as e:
            message = _("Unable to _build_sps_package_add_xml {} {} {}").format(
                self.collection.acron, sps_pkg_name, sps_xml_name
            )
            exc_type, exc_value, exc_traceback = sys.exc_info()
            self.add_incident(
                collection_acron=self.collection.acron,
                app_name="migration",
                user=user,
                context="build-sps-package",
                item_name="xml",
                item_id=sps_xml_name,
                e=e,
                message=message,
                exc_traceback=exc_traceback,
            )

    def generate_sps_package(
        self,
        user,
        body_and_back_xml=False,
        html_to_xml=False,
    ):
        try:
            with TemporaryDirectory() as output_folder:
                sps_pkg_zip_path = self.build_sps_package(user, output_folder)

                self.sps_pkg = SPSPkg.create_or_update(
                    user,
                    sps_pkg_zip_path,
                    package_choices.PKG_ORIGIN_MIGRATION,
                    reset_failures=True,
                    is_published=True,
                )
                self.sps_pkg.add_annotation(
                    user=user,
                    annotation_type=package_choices.ANNOTATION_WARNING,
                    annotation_subtype=self.xml_status,
                    annotation_text=_("XML status {}").format(self.xml_status),
                    detail={"package_xml_status": self.xml_status},
                )

                if self.missing_assets:
                    self.sps_pkg.add_annotation(
                        user=user,
                        annotation_type=package_choices.ANNOTATION_PKG_ERROR,
                        annotation_subtype=package_choices.PKG_ASSETS_STATUS_MISSING,
                        annotation_text=_("Missing assets"),
                        detail={"missing_assets": self.missing_assets},
                    )
                self.xml_status = choices.DOC_GENERATED_SPS_PKG
                self.save()

        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            item_id = f"{self.pid}"
            message = _("Unable to generate SPS Package {}").format(item_id)
            self.add_incident(
                collection_acron=self.collection.acron,
                app_name="migration",
                user=user,
                context="generate_sps_pkg_name",
                item_name="sps_pkg_name",
                item_id=item_id,
                message=message,
                e=e,
                exc_traceback=exc_traceback,
            )


def body_and_back_directory_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/user_<id>/<filename>
    issue_pid = instance.migrated_issue.pid
    return (
        f"migration/{issue_pid[:9]}/"
        f"{issue_pid[9:13]}/"
        f"{issue_pid[13:]}/"
        f"{instance.pkg_name}/"
        f"body-back/"
        f"{instance.version}/"
        f"{filename}"
    )


class BodyAndBackFile(BasicXMLFile, Orderable):
    migrated_document_html = ParentalKey("MigratedDocumentHTML", related_name="bb_file")

    file = models.FileField(
        upload_to=body_and_back_directory_path, null=True, blank=True
    )
    version = models.IntegerField()

    panels = [
        FieldPanel("file"),
        FieldPanel("version"),
    ]

    class Meta:
        indexes = [
            models.Index(fields=["version"]),
        ]

    def autocomplete_label(self):
        return f"{self.migrated_document_html} {self.version}"

    def __str__(self):
        return f"{self.migrated_document_html} {self.version}"

    @classmethod
    def get(cls, migrated_document_html, version):
        if not migrated_document_html:
            raise ValueError("BodyAndBackFile.requires migrated_document_html")
        if not version:
            raise ValueError("BodyAndBackFile.requires version")
        return cls.objects.get(
            migrated_document_html=migrated_document_html,
            version=version,
        )

    @classmethod
    def create_or_update(cls, user, migrated_document_html, version, file_content):
        try:
            obj = cls.get(migrated_document_html, version)
            obj.updated_by = user
            obj.updated = datetime.utcnow()
        except cls.MultipleObjectsReturned:
            cls.objects.filter(
                migrated_document_html=migrated_document_html, version=version
            ).delete()
            obj = cls()
            obj.creator = user
            obj.migrated_document_html = migrated_document_html
            obj.version = version
            obj.save()
        except cls.DoesNotExist:
            obj = cls()
            obj.creator = user
            obj.migrated_document_html = migrated_document_html
            obj.version = version
            obj.save()
        try:
            # cria / atualiza arquivo
            obj.save_file(obj.filename, file_content)
            obj.save()
            return obj
        except Exception as e:
            raise exceptions.CreateOrUpdateBodyAndBackFileError(
                _(
                    "Unable to create_or_update_body and back file {} {} {} {} {}"
                ).format(migrated_document_html, version, type(e), e)
            )


class MigratedDocumentHTML(MigratedDocument):
    conversion_status = models.CharField(
        _("status"),
        max_length=25,
        choices=choices.HTML2XML_STATUS,
        default=choices.HTML2XML_NOT_EVALUATED,
    )
    translation_files = models.ManyToManyField(TranslationFile)
    bb_files = models.ManyToManyField(BodyAndBackFile)
    report = models.ForeignKey(
        Html2xmlReport, on_delete=models.SET_NULL, null=True, blank=True
    )

    panel_status = [
        FieldPanel("conversion_status"),
        FieldPanel("xml_status"),
        FieldPanel("report"),
    ]

    panel_translation_files = [
        InlinePanel(
            "translation_file",
            label=_("Translation files"),
            related_name="translation_file",
        ),
    ]

    panel_bb_files = [
        InlinePanel(
            "bb_file", label=_("Body and Back XML files"), related_name="bb_file"
        ),
    ]

    edit_handler = TabbedInterface(
        [
            ObjectList(panel_status, heading=_("Status")),
            ObjectList(panel_migrated_data, heading=_("Migration Data")),
            ObjectList(panel_renditions, heading=_("Renditions")),
            ObjectList(panel_translation_files, heading=_("Translation files")),
            ObjectList(panel_bb_files, heading=_("Body and Back XML files")),
            ObjectList(panel_files, heading=_("XML")),
        ]
    )

    def autocomplete_label(self):
        return f"{self.scielo_issue} {self.pkg_name}"

    class Meta:
        indexes = [
            models.Index(fields=["conversion_status"]),
        ]

    @classmethod
    def get(
        cls,
        collection=None,
        pid=None,
        migrated_issue=None,
        pkg_name=None,
    ):
        if collection and pid:
            return cls.objects.get(collection=collection, pid=pid)

        if pkg_name and pid and collection:
            return cls.objects.get(
                collection=collection, migrated_issue__pid=pid[1:-5], pkg_name=pkg_name
            )

        if migrated_issue and pkg_name:
            return cls.objects.get(migrated_issue=migrated_issue, pkg_name=pkg_name)
        raise ValueError(
            "MigratedDocument.get requires collection, pid, migrated_issue, pkg_name"
        )

    @classmethod
    def create_or_update(
        cls,
        collection=None,
        pid=None,
        migrated_issue=None,
        pkg_name=None,
        user=None,
        isis_created_date=None,
        isis_updated_date=None,
        data=None,
        status=None,
        sps_pkg_name=None,
        force_update=None,
    ):
        try:
            obj = cls.get(
                collection=collection,
                pid=pid,
                migrated_issue=migrated_issue,
                pkg_name=pkg_name,
            )
            if (
                force_update
                or not obj.isis_updated_date
                or obj.isis_updated_date < isis_updated_date
                or obj.data != data
            ):
                obj.updated_by = user
            else:
                return obj
        except cls.MultipleObjectsReturned as e:
            if collection and pid:
                cls.objects.filter(
                    collection=collection,
                    pid=pid,
                ).delete()

            if migrated_issue and pkg_name:
                cls.objects.filter(
                    migrated_issue=migrated_issue,
                    pkg_name=pkg_name,
                ).delete()

            obj = cls()
            obj.creator = user
        except cls.DoesNotExist:
            obj = cls()
            obj.creator = user
        try:
            obj.data = data or obj.data
            collection = collection or obj.collection
            collection = (
                collection or obj.migrated_issue and obj.migrated_issue.collection
            )
            obj.collection = collection or obj.collection
            obj.pid = pid or obj.pid
            obj.migrated_issue = migrated_issue or obj.migrated_issue
            obj.pkg_name = pkg_name or obj.pkg_name
            obj.isis_created_date = isis_created_date
            obj.isis_updated_date = isis_updated_date
            obj.status = status or obj.status
            obj.save()
            return obj
        except Exception as e:
            raise exceptions.CreateOrUpdateMigratedDocumentError(
                _("Unable to create_or_update_migrated_document {} {} {} {}").format(
                    collection, pid, type(e), e
                )
            )

    @property
    def document(self):
        if not hasattr(self, "_document") or self._document is None:
            self._document = classic_ws.Document(self.data)
        return self._document

    @property
    def p_records(self):
        try:
            return self.document.p_records
        except Exception as e:
            return None

    @property
    def record_types(self):
        try:
            return self.document.record_types
        except Exception as e:
            return None

    def html_to_xml(
        self,
        user,
        body_and_back_xml,
        html_to_xml,
    ):
        logging.info("xml-body-and-back")
        self._generate_xml_body_and_back(user)
        logging.info("_generate_xml_from_html")
        self._generate_xml_from_html(user)

        try:
            self.report = Html2xmlReport.create_or_update(
                user, self.bb_files.first(), self
            )
        except Exception as e:
            item_id = self.pid
            message = _("Unable to generate html to xml conversion report {}").format(
                item_id
            )
            exc_type, exc_value, exc_traceback = sys.exc_info()
            self.add_incident(
                collection_acron=self.collection.acron,
                app_name="migration",
                user=user,
                context="html-to-xml-conversion-report",
                item_name="document",
                item_id=item_id,
                message=message,
                e=e,
                exc_traceback=exc_traceback,
            )

    @property
    def translations(self):
        """
        {
            "pt": {1: "", 2: ""},
            "es": {1: "", 2: ""},
        }
        """
        part = {1: "before references", 2: "after references"}
        xhtmls = {}
        for item in self.translation_files.iterator():
            hc = HTMLContent(item.text)
            lang = item.lang.code2
            xhtmls.setdefault(lang, {})
            xhtmls[lang][part[item.part]] = hc.content
        return xhtmls

    # def _generate_xml_body_and_back(self, user):
    #     item_id = f"{self}"
    #     try:
    #         # obtém um XML com body e back a partir HTML principal + traduções
    #         self.document.generate_body_and_back_from_html(self.translations)

    #         # guarda cada versão de body/back
    #         for i, xml_body_and_back in enumerate(
    #             self.document.xml_body_and_back, start=1
    #         ):
    #             item_id = f"{self} {i}"
    #             self.bb_files.add(
    #                 BodyAndBackFile.create_or_update(
    #                     user=user,
    #                     migrated_issue=self.migrated_issue,
    #                     pkg_name=self.pkg_name,
    #                     version=i,
    #                     file_content=xml_body_and_back,
    #                 )
    #             )
    #     except Exception as e:
    #         message = _("Unable to generate body and back from HTML {}").format(
    #             item_id
    #         )
    #         exc_type, exc_value, exc_traceback = sys.exc_info()
    #         self.incident_report = IncidentReport.create_or_update(
    #             Incident.create(
    # collection_acron=collection.acron,
    # app_name="migration",
    #                 item_name="document",
    #                 item_id=item_id,
    #                 message=message,
    #                 context="xml-body-and-back",
    #                 e=e,
    #                 user=user,
    #                 exc_traceback=exc_traceback,
    #             )
    #         )

    def _generate_xml_body_and_back(self, user):
        item_id = f"{self}"
        try:
            # obtém um XML com body e back a partir HTML principal + traduções
            self.document.generate_body_and_back_from_html(self.translations)
        except Exception as e:
            message = _("Unable to generate body and back from HTML {}").format(item_id)
            exc_type, exc_value, exc_traceback = sys.exc_info()
            self.add_incident(
                collection_acron=self.collection.acron,
                app_name="migration",
                user=user,
                context="xml-body-and-back",
                item_name="document",
                item_id=item_id,
                message=message,
                e=e,
                exc_traceback=exc_traceback,
            )
        else:
            # guarda cada versão de body/back
            for i, xml_body_and_back in enumerate(
                self.document.xml_body_and_back, start=1
            ):
                try:
                    item_id = f"{self} {i}"
                    self.bb_files.add(
                        BodyAndBackFile.create_or_update(
                            user=user,
                            migrated_document_html=self,
                            version=i,
                            file_content=xml_body_and_back,
                        )
                    )
                except Exception as e:
                    message = _("Unable to save body and back xml {}").format(item_id)
                    exc_type, exc_value, exc_traceback = sys.exc_info()
                    self.add_incident(
                        collection_acron=self.collection.acron,
                        app_name="migration",
                        user=user,
                        context="xml-body-and-back",
                        item_name="document",
                        item_id=item_id,
                        message=message,
                        e=e,
                        exc_traceback=exc_traceback,
                    )

    def _generate_xml_from_html(self, user):
        try:
            xml_content = self.document.generate_full_xml(
                self.bb_files.latest("version").text
            )
            self.save_file(self.pkg_name + ".xml", xml_content.strip())
        except Exception as e:
            item_id = f"{self}"
            message = _("Unable to generate XML from HTML {}").format(item_id)
            exc_type, exc_value, exc_traceback = sys.exc_info()
            self.add_incident(
                collection_acron=self.collection.acron,
                app_name="migration",
                user=user,
                context="html_to_xml",
                item_name="document",
                item_id=item_id,
                message=message,
                e=e,
                exc_traceback=exc_traceback,
            )


def generated_xml_report_directory_path(instance, filename):
    issue_pid = instance.html.migrated_issue.pid
    html = instance.html
    return (
        f"migration/{issue_pid[:9]}/"
        f"{issue_pid[9:13]}/"
        f"{issue_pid[13:]}/"
        f"{html.pkg_name}/"
        f"generated_xml/"
        f"{html.version}/"
        f"{filename}"
    )


class Html2xmlReport(CommonControlField):
    html = models.ForeignKey(
        BodyAndBackFile, on_delete=models.SET_NULL, null=True, blank=True
    )
    xml = models.ForeignKey(
        MigratedDocumentHTML, on_delete=models.SET_NULL, null=True, blank=True
    )

    comments = models.TextField(null=True, blank=True)
    report = models.FileField(
        upload_to=generated_xml_report_directory_path, null=True, blank=True
    )

    empty_body = models.BooleanField(null=True, blank=True)

    attention_demands = models.IntegerField(null=True, blank=True)

    html_img_total = models.IntegerField(null=True, blank=True)
    html_table_total = models.IntegerField(null=True, blank=True)

    xml_supplmat_total = models.IntegerField(null=True, blank=True)
    xml_media_total = models.IntegerField(null=True, blank=True)
    xml_fig_total = models.IntegerField(null=True, blank=True)
    xml_table_wrap_total = models.IntegerField(null=True, blank=True)
    xml_eq_total = models.IntegerField(null=True, blank=True)
    xml_graphic_total = models.IntegerField(null=True, blank=True)
    xml_inline_graphic_total = models.IntegerField(null=True, blank=True)

    xml_ref_elem_citation_total = models.IntegerField(null=True, blank=True)
    xml_ref_mixed_citation_total = models.IntegerField(null=True, blank=True)
    xml_text_lang_total = models.IntegerField(null=True, blank=True)
    article_type = models.CharField(null=True, blank=True, max_length=32)

    panels = [
        # AutocompletePanel("migrated_document"),
        FieldPanel("html"),
        FieldPanel("xml"),
        FieldPanel("status"),
        FieldPanel("comments"),
        FieldPanel("report"),
        FieldPanel("attention_demands"),
        FieldPanel("article_type"),
        FieldPanel("html_table_total"),
        FieldPanel("html_img_total"),
        FieldPanel("empty_body"),
        FieldPanel("xml_text_lang_total"),
        FieldPanel("xml_table_wrap_total"),
        FieldPanel("xml_supplmat_total"),
        FieldPanel("xml_media_total"),
        FieldPanel("xml_fig_total"),
        FieldPanel("xml_eq_total"),
        FieldPanel("xml_graphic_total"),
        FieldPanel("xml_inline_graphic_total"),
        FieldPanel("xml_ref_elem_citation_total"),
        FieldPanel("xml_ref_mixed_citation_total"),
    ]

    def autocomplete_label(self):
        return f"{self.xml}"

    class Meta:
        indexes = [
            models.Index(fields=["attention_demands"]),
        ]

    def __str__(self):
        return f"{self.xml}"

    @classmethod
    def get(cls, html, xml):
        return cls.objects.get(xml=xml, html=html)

    @classmethod
    def create_or_update(cls, user, html, xml):
        try:
            obj = cls.get(html, xml)
            obj.updated_by = user
        except cls.DoesNotExist:
            obj = cls()
            obj.creator = user
            obj.html = html
            obj.xml = xml
        obj.evaluate_xml()
        obj.save()
        return obj

    def save_report(self, name, data):
        content = json.dumps(data)
        self.report.save(name, ContentFile(content))

    def tostring(self, node):
        return etree.tostring(node, encoding="utf-8").decode("utf-8")

    def get_a_href_stats(self, html, xml):
        nodes = html.xpath(".//a[@href]")
        for a in nodes:
            data = {}
            data["html"] = self.tostring(a)

            xml_nodes = []
            href = a.get("href")
            if "img/revistas" in href:
                name, ext = os.path.splitext(href)
                if ".htm" not in ext:
                    for item in xml.xpath(f".//xref[text()='{a.text}']"):
                        xml_nodes.append(self.tostring(item))

                    for item in xml.xpath(
                        f".//graphic[@xlink:href='{href}']",
                        namespaces={"xlink": "http://www.w3.org/1999/xlink"},
                    ):
                        xml_nodes.append(self.tostring(item))
            elif href.startswith("#"):
                for item in xml.xpath(f".//xref[text()='{a.text}']"):
                    xml_nodes.append(self.tostring(item))
            elif "@" in href or "@" in a.text:
                for item in xml.xpath(f".//email[text()='{a.text}']"):
                    xml_nodes.append(self.tostring(item))
            else:
                for item in xml.xpath(f".//ext-link[text()='{a.text}']"):
                    xml_nodes.append(self.tostring(item))
            data["xml"] = xml_nodes
            yield data

    def get_src_stats(self, html, xml):
        self.html_img_total = len(html.xpath(".//img[@src]"))
        nodes = html.xpath(".//*[@src]")
        for a in nodes:
            data = {}
            data["html"] = self.tostring(a)
            xml_nodes = []
            src = a.get("src")
            if "img/revistas" in src or src.startswith("/pdf"):
                if a.tag == "img":
                    for item in xml.xpath(
                        f".//graphic[@xlink:href='{src}'] | .//inline-graphic[@xlink:href='{src}']",
                        namespaces={"xlink": "http://www.w3.org/1999/xlink"},
                    ):
                        xml_nodes.append(self.tostring(item))
                else:
                    for item in xml.xpath(
                        f".//*[@xlink:href='{src}']",
                        namespaces={"xlink": "http://www.w3.org/1999/xlink"},
                    ):
                        xml_nodes.append(self.tostring(item))
            else:
                for item in xml.xpath(f".//*[@xlink:href='{src}']"):
                    xml_nodes.append(self.tostring(item))
            data["xml"] = xml_nodes
            yield data

    def get_a_name_stats(self, html, xml):
        for node in html.xpath(".//a[@name]"):
            data = {}
            data["html"] = self.tostring(node)
            xml_nodes = []
            name = node.get("name")
            if not name:
                continue
            if name.isalpha():
                for item in xml.xpath(f".//*[@id='{name}']"):
                    xml_nodes.append(self.tostring(item))
            elif name[0] == "t" and name[-1].isdigit():
                for item in xml.xpath(f".//table-wrap[@id='{name}']"):
                    xml_nodes.append(self.tostring(item))
            elif name[0] == "f" and name[-1].isdigit():
                for item in xml.xpath(f".//fig[@id='{name}']"):
                    xml_nodes.append(self.tostring(item))
            elif name[-1].isdigit():
                for item in xml.xpath(f".//*[@id='{name}']"):
                    xml_nodes.append(self.tostring(item))
            data["xml"] = xml_nodes
            yield data

    def get_xml_stats(self, xml):
        body = xml.find(".//body")
        self.empty_body = body is None or not body.xpath(".//text()")
        self.xml_supplmat_total = len(xml.xpath(".//supplementary-material")) + len(
            xml.xpath(".//inline-supplementary-material")
        )
        self.xml_media_total = len(xml.xpath(".//media"))
        self.xml_fig_total = len(xml.xpath(".//fig[@id]")) + len(
            xml.xpath(".//fig-group[@id]")
        )
        self.xml_table_wrap_total = len(xml.xpath(".//table-wrap[@id]"))
        self.xml_eq_total = len(xml.xpath(".//disp-formula[@id]"))
        self.xml_graphic_total = len(xml.xpath(".//graphic"))
        self.xml_inline_graphic_total = len(xml.xpath(".//inline-graphic"))
        self.xml_ref_elem_citation_total = len(xml.xpath(".//element-citation"))
        self.xml_ref_mixed_citation_total = len(xml.xpath(".//mixed-citation"))
        self.xml_text_lang_total = (
            len(xml.xpath(".//sub-article[@article-type='translation']")) + 1
        )
        self.article_type = xml.find(".").get("article-type")

    def evaluate_xml(self):
        self.html_img_total = 0
        self.html_table_total = 0

        self.xml_supplmat_total = 0
        self.xml_media_total = 0
        self.xml_fig_total = 0
        self.xml_table_wrap_total = 0
        self.xml_eq_total = 0
        self.xml_graphic_total = 0
        self.xml_inline_graphic_total = 0
        self.xml_ref_elem_citation_total = 0
        self.xml_ref_mixed_citation_total = 0
        self.xml_text_lang_total = 0

        html = _fromstring(self.html.text)
        xml = _fromstring(self.xml.text)

        if html is not None and xml is not None:
            self.get_xml_stats(xml)

            self.html_table_total = len(html.xpath(".//table"))
            self.html_img_total = len(html.xpath(".//img[@src]"))

            items = []
            items.extend(self.get_a_href_stats(html, xml))
            items.extend(self.get_src_stats(html, xml))
            items.extend(self.get_a_name_stats(html, xml))

            self.save_report(f"{self}.json", items)

        self.attention_demands = 0
        if self.html_table_total != self.xml_table_wrap_total:
            self.attention_demands += 1

        if (
            self.html_img_total
            != self.xml_graphic_total + self.xml_inline_graphic_total
        ):
            self.attention_demands += 1

        self.attention_demands = 0
        if self.empty_body:
            self.attention_demands += 1

        if self.xml_ref_elem_citation_total != self.xml_ref_mixed_citation_total:
            self.attention_demands += 1

        if (
            self.xml_ref_elem_citation_total == 0
            or self.xml_ref_mixed_citation_total == 0
        ):
            self.attention_demands += 1

        if self.xml_text_lang_total > 1:
            self.attention_demands += 1

        self.attention_demands += self.xml_inline_graphic_total
        self.attention_demands += self.xml_graphic_total
        self.attention_demands += self.xml_eq_total
        self.attention_demands += self.xml_table_wrap_total
        self.attention_demands += self.xml_fig_total
        self.attention_demands += self.xml_media_total
        self.attention_demands += self.xml_supplmat_total
        self.attention_demands += self.html_table_total

        if self.attention_demands == 0:
            self.xml.conversion_status = choices.HTML2XML_AUTO_APPROVED
        else:
            self.xml.conversion_status = choices.HTML2XML_NOT_EVALUATED
        self.save()
