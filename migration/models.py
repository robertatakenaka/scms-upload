import logging
import os
from datetime import datetime

from django.core.files.base import ContentFile
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from packtools.sps.pid_provider.xml_sps_lib import XMLWithPre

from collection.models import Collection, Language
from core.forms import CoreAdminModelForm
from core.models import CommonControlField
from issue.models import SciELOIssue
from journal.models import SciELOJournal
from scielo_classic_website.htmlbody.html_body import HTMLContent

from . import choices, exceptions


def now():
    return datetime.utcnow().isoformat().replace(":", "-").replace(".", "-")


class MigratedFileGetError(Exception):
    ...


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
        creator=None,
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


class MigratedData(CommonControlField):
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

    class Meta:
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["isis_updated_date"]),
        ]


class MigrationFailure(CommonControlField):
    action_name = models.TextField(_("Action"), null=True, blank=True)
    message = models.TextField(_("Message"), null=True, blank=True)
    migrated_item_name = models.TextField(_("Item name"), null=True, blank=True)
    migrated_item_id = models.TextField(_("Item id"), null=True, blank=True)
    exception_type = models.TextField(_("Exception Type"), null=True, blank=True)
    exception_msg = models.TextField(_("Exception Msg"), null=True, blank=True)
    collection_acron = models.TextField(_("Collection acron"), null=True, blank=True)
    traceback = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["action_name"]),
        ]

    @classmethod
    def create(
        cls,
        message=None,
        action_name=None,
        e=None,
        creator=None,
        migrated_item_name=None,
        migrated_item_id=None,
        collection_acron=None,
    ):
        # exc_type, exc_value, exc_traceback = sys.exc_info()
        obj = cls()
        obj.collection_acron = collection_acron
        obj.action_name = action_name
        obj.migrated_item_name = migrated_item_name
        obj.migrated_item_id = migrated_item_id
        obj.message = message
        obj.exception_msg = str(e)
        obj.exception_type = str(type(e))
        obj.creator = creator
        obj.save()
        return obj


def migrated_files_directory_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/user_<id>/<filename>
    issue_pid = instance.migrated_issue.issue_pid
    return (
        f"migration/{issue_pid[:9]}/"
        f"{issue_pid[9:13]}/"
        f"{issue_pid[13:]}/{instance.pkg_name}/"
        f"{filename}"
    )


class MigratedFile(CommonControlField):
    migrated_issue = models.ForeignKey(
        "MigratedIssue", on_delete=models.SET_NULL, null=True, blank=True
    )
    file = models.FileField(
        upload_to=migrated_files_directory_path, null=True, blank=True
    )
    # bases/pdf/acron/volnum/pt_a01.pdf
    original_path = models.TextField(_("Original Path"), null=True, blank=True)
    # /pdf/acron/volnum/pt_a01.pdf
    original_href = models.TextField(_("Original href"), null=True, blank=True)
    # pt_a01.pdf
    original_name = models.TextField(_("Original name"), null=True, blank=True)
    # ISSN-acron-vol-num-suppl
    sps_pkg_name = models.TextField(_("New name"), null=True, blank=True)
    # a01
    pkg_name = models.TextField(_("Package name"), null=True, blank=True)
    # rendition
    category = models.CharField(
        _("Issue File Category"),
        max_length=20,
        null=True,
        blank=True,
    )
    lang = models.ForeignKey(Language, null=True, blank=True, on_delete=models.SET_NULL)
    part = models.CharField(_("Part"), max_length=6, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["pkg_name"]),
            models.Index(fields=["migrated_issue"]),
            models.Index(fields=["lang"]),
            models.Index(fields=["part"]),
            models.Index(fields=["category"]),
            models.Index(fields=["original_href"]),
            models.Index(fields=["original_name"]),
            models.Index(fields=["sps_pkg_name"]),
        ]

    @classmethod
    def get_original_href(self, original_path):
        try:
            return original_path[original_path.find("/") :]
        except:
            pass

    def __str__(self):
        if self.original_path:
            return self.original_path
        return f"{self.pkg_name} {self.category} {self.lang} {self.part}"

    def save_file(self, name, content):
        if self.file:
            try:
                with open(self.file.path, "rb") as fp:
                    c = fp.read()
                    if c == content:
                        logging.info("skip save file")
                        return
            except Exception as e:
                pass
        self.file.save(name, ContentFile(content))
        logging.info(f"Saved {self.file.path}")

    @property
    def text(self):
        if self.category == "xml":
            with open(self.file.path, "r") as fp:
                return fp.read()
        if self.category == "html":
            try:
                with open(self.file.path, mode="r", encoding="iso-8859-1") as fp:
                    return fp.read()
            except:
                with open(self.file.path, mode="r", encoding="utf-8") as fp:
                    return fp.read()

    @property
    def xml_with_pre(self):
        if self.category == "xml":
            for item in XMLWithPre.create(path=self.file.path):
                return item

    @classmethod
    def get(
        cls,
        migrated_issue,
        original_path=None,
        original_name=None,
        original_href=None,
        pkg_name=None,
        category=None,
        part=None,
        lang=None,
    ):
        if not migrated_issue:
            raise MigratedFileGetError(_("MigratedFile.get requires migrated_issue"))
        if original_href:
            # /pdf/acron/volume/file.pdf
            return cls.objects.get(
                migrated_issue=migrated_issue,
                original_href=original_href,
            )
        if original_name:
            # file.pdf
            return cls.objects.get(
                migrated_issue=migrated_issue,
                original_name=original_name,
            )
        if original_path:
            # bases/pdf/acron/volume/file.pdf
            return cls.objects.get(
                original_path=original_path,
            )

        if category and lang and part and pkg_name:
            # bases/pdf/acron/volume/file.pdf
            return cls.objects.get(
                migrated_issue=migrated_issue,
                pkg_name=pkg_name,
                category=category,
                lang=lang,
                part=part,
            )
        raise MigratedFileGetError(
            _(
                "MigratedFile.get requires original_path or original_name or"
                " original_href or pkg_name or category and lang and part"
            )
        )

    def is_out_of_date(self, file_content):
        if not self.file:
            return True
        try:
            with open(self.file.path, "rb") as fp:
                c = fp.read()
            return c != file_content
        except Exception as e:
            return True

    @classmethod
    def create_or_update(
        cls,
        migrated_issue,
        original_path=None,
        source_path=None,
        file_content=None,
        file_name=None,
        category=None,
        lang=None,
        part=None,
        pkg_name=None,
        sps_pkg_name=None,
        creator=None,
        force_update=None,
    ):
        try:
            input_data = dict(
                migrated_issue=migrated_issue,
                original_path=original_path,
                # original_name=original_name,
                # original_href=original_href,
                pkg_name=pkg_name,
                lang=lang,
                part=part,
                category=category,
            )
            logging.info(f"Create or update MigratedFile {input_data}")

            if source_path:
                with open(source_path, "rb") as fp:
                    file_content = fp.read()

            obj = cls.get(**input_data)

            if force_update or obj.is_out_of_date(file_content):
                logging.info(f"Update MigratedFile {input_data}")
                obj.updated_by = creator
            else:
                logging.info(f"MigratedFile is already up-to-date")
                return obj
        except cls.DoesNotExist:
            logging.info(f"Create MigratedFile {input_data}")
            obj = cls()
            obj.creator = creator

        try:
            obj.migrated_issue = migrated_issue
            obj.original_path = original_path
            obj.original_name = original_path and os.path.basename(original_path)
            obj.original_href = cls.get_original_href(original_path)
            obj.sps_pkg_name = sps_pkg_name
            obj.pkg_name = pkg_name
            obj.category = category
            if lang:
                obj.lang = Language.get_or_create(code2=lang, creator=creator)
            obj.part = part
            obj.save()

            # cria / atualiza arquivo
            obj.save_file(file_name or obj.filename, file_content)
            obj.save()
            logging.info(f"Created {obj}")
            return obj
        except Exception as e:
            raise exceptions.CreateOrUpdateMigratedFileError(
                _("Unable to get_or_create_migrated_issue_file {} {} {} {}").format(
                    migrated_issue, original_path, type(e), e
                )
            )

    @property
    def filename(self):
        collection_acron = self.migrated_issue.migrated_journal.collection.acron
        journal_acron = self.migrated_issue.migrated_journal.scielo_journal.acron
        issue_folder = self.migrated_issue.issue_folder
        basename = os.path.basename(self.original_path)
        return f"{collection_acron}_{journal_acron}_{issue_folder}_{basename}"


class MigratedJournal(MigratedData):
    """
    Dados migrados do periódico do site clássico
    """

    scielo_journal = models.ForeignKey(
        SciELOJournal, on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        indexes = [
            models.Index(fields=["scielo_journal"]),
        ]

    def __str__(self):
        return f"{self.scielo_journal.scielo_issn} ({self.scielo_journal.acron})"

    @classmethod
    def get(cls, collection=None, scielo_issn=None, scielo_journal=None):
        logging.info(
            f"MigratedJournal.create_or_update collection={collection} scielo_issn={scielo_issn} scielo_journal={scielo_journal} "
        )
        if collection and scielo_issn:
            return cls.objects.get(
                scielo_journal__collection=collection,
                scielo_journal__scielo_issn=scielo_issn,
            )
        if scielo_journal:
            return cls.objects.get(
                scielo_journal=scielo_journal,
            )

    @classmethod
    def create_or_update(
        cls,
        scielo_journal,
        creator=None,
        isis_created_date=None,
        isis_updated_date=None,
        data=None,
        status=None,
        force_update=None,
    ):
        logging.info(f"MigratedJournal.create_or_update {scielo_journal}")
        try:
            obj = cls.get(scielo_journal=scielo_journal)

            if (
                force_update
                or not obj.isis_updated_date
                or obj.isis_updated_date < isis_updated_date
                or data != obj.data
            ):
                logging.info("Update MigratedJournal {}".format(obj))
                obj.updated_by = creator
            else:
                logging.info("Skip updating journal")
                return obj
        except cls.DoesNotExist:
            obj = cls()
            obj.scielo_journal = scielo_journal
            obj.creator = creator
            logging.info("Create MigratedJournal {}".format(obj))

        try:
            obj.isis_created_date = isis_created_date or obj.isis_created_date
            obj.isis_updated_date = isis_updated_date or obj.isis_updated_date
            obj.status = status or obj.status
            obj.data = data or obj.data
            obj.save()
            logging.info("Created / Updated MigratedJournal {}".format(obj))
            return obj
        except Exception as e:
            raise exceptions.CreateOrUpdateMigratedJournalError(
                _("Unable to create_or_update_migrated_journal {} {} {}").format(
                    scielo_journal, type(e), e
                )
            )

    @classmethod
    def journals(cls, collection_acron, status):
        return cls.objects.filter(
            scielo_journal__collection__acron=collection_acron,
            status=status,
        ).iterator()

    @property
    def collection(self):
        return self.scielo_journal.collection

    @property
    def acron(self):
        return self.scielo_journal.acron

    @property
    def scielo_issn(self):
        return self.scielo_journal.scielo_issn


class MigratedIssue(MigratedData):
    scielo_issue = models.ForeignKey(
        SciELOIssue, on_delete=models.SET_NULL, null=True, blank=True
    )
    migrated_journal = models.ForeignKey(
        MigratedJournal, on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        indexes = [
            models.Index(fields=["scielo_issue"]),
            models.Index(fields=["migrated_journal"]),
        ]

    def __unicode__(self):
        return f"{self.scielo_issue}"

    def __str__(self):
        return f"{self.scielo_issue}"

    @property
    def issue_pid(self):
        return self.scielo_issue.issue_pid

    @property
    def issue_folder(self):
        return self.scielo_issue.issue_folder

    @property
    def publication_year(self):
        return self.scielo_issue.official_issue.publication_year

    @classmethod
    def get(
        cls,
        collection_acron=None,
        journal_acron=None,
        issue_folder=None,
        scielo_issue=None,
    ):
        if scielo_issue:
            return cls.objects.get(scielo_issue=scielo_issue)
        if collection_acron and journal_acron and issue_folder:
            return cls.objects.get(
                migrated_journal__scielo_journal__collection__acron=collection_acron,
                migrated_journal__scielo_journal__acron=journal_acron,
                scielo_issue__issue_folder=issue_folder,
            )
        raise ValueError(
            "MigratedIssue.get requires scielo_issue or collection and journal_acron and issue_folder"
        )

    @classmethod
    def create_or_update(
        cls,
        scielo_issue,
        migrated_journal,
        creator=None,
        isis_created_date=None,
        isis_updated_date=None,
        status=None,
        data=None,
        force_update=None,
    ):
        logging.info("Create or Update MigratedIssue {}".format(scielo_issue))
        try:
            obj = cls.objects.get(scielo_issue=scielo_issue)
            if (
                force_update
                or not obj.isis_updated_date
                or obj.isis_updated_date < isis_updated_date
                or obj.data != data
            ):
                logging.info(f"Update MigratedIssue {obj}")
                obj.updated_by = creator
            else:
                logging.info(f"Skip updating issue {obj}")
                return obj
        except cls.DoesNotExist:
            obj = cls()
            obj.scielo_issue = scielo_issue
            obj.creator = creator
            logging.info(f"Create MigratedIssue {obj}")

        try:
            obj.migrated_journal = migrated_journal or obj.migrated_journal
            obj.isis_created_date = isis_created_date or obj.isis_created_date
            obj.isis_updated_date = isis_updated_date or obj.isis_updated_date
            obj.status = status or obj.status
            obj.data = data or obj.data
            obj.save()
            logging.info(f"Created / Updated MigratedIssue {obj}")
            return obj
        except Exception as e:
            raise exceptions.CreateOrUpdateMigratedIssueError(
                _("Unable to create_or_update_migrated_issue {} {} {}").format(
                    scielo_issue, type(e), e
                )
            )


class MigratedDocument(MigratedData):
    migrated_issue = models.ForeignKey(
        MigratedIssue, null=True, blank=True, on_delete=models.SET_NULL
    )
    pid = models.CharField(_("PID"), max_length=23, null=True, blank=True)
    pkg_name = models.TextField(_("Package name"), null=True, blank=True)
    sps_pkg_name = models.TextField(_("New Package name"), null=True, blank=True)
    file_type = models.CharField(_("File type"), max_length=5, null=True, blank=True)
    missing_assets = models.JSONField(null=True, blank=True)

    def __unicode__(self):
        return f"{self.migrated_issue} {self.pkg_name}"

    def __str__(self):
        return f"{self.migrated_issue} {self.pkg_name}"

    class Meta:
        indexes = [
            models.Index(fields=["migrated_issue"]),
            models.Index(fields=["pid"]),
            models.Index(fields=["pkg_name"]),
        ]

    @classmethod
    def get(cls, migrated_issue, pid=None, pkg_name=None):
        if pid:
            return cls.objects.get(
                migrated_issue=migrated_issue,
                pid=pid,
            )
        if pkg_name:
            return cls.objects.get(
                migrated_issue=migrated_issue,
                pkg_name=pkg_name,
            )

    @classmethod
    def create_or_update(
        cls,
        migrated_issue,
        pid=None,
        pkg_name=None,
        creator=None,
        isis_created_date=None,
        isis_updated_date=None,
        data=None,
        status=None,
        sps_pkg_name=None,
        file_type=None,
        force_update=None,
    ):
        key = dict(
            migrated_issue=migrated_issue,
            pid=pid,
            pkg_name=pkg_name,
        )
        logging.info(f"Create or Update MigratedDocument {key}")

        try:
            obj = cls.get(
                migrated_issue=migrated_issue,
                pid=pid,
                pkg_name=pkg_name,
            )
            if (
                force_update
                or not obj.isis_updated_date
                or obj.isis_updated_date < isis_updated_date
                or obj.data != data
            ):
                logging.info("Update MigratedDocument {}".format(obj))
                obj.updated_by = creator
            else:
                logging.info("Skip updating document {}".format(obj))
                return obj
        except cls.MultipleObjectsReturned as e:
            logging.exception(e)
            cls.objects.filter(
                migrated_issue=migrated_issue,
                pid=pid,
                pkg_name=pkg_name,
            ).delete()
            obj = cls()
            obj.migrated_issue = migrated_issue
            obj.creator = creator
            logging.info("Create MigratedDocument {}".format(obj))
        except cls.DoesNotExist:
            obj = cls()
            obj.migrated_issue = migrated_issue
            obj.creator = creator
            logging.info("Create MigratedDocument {}".format(obj))
        try:
            obj.file_type = file_type or obj.file_type
            obj.pkg_name = pkg_name or obj.pkg_name
            obj.pid = pid or obj.pid
            obj.isis_created_date = isis_created_date
            obj.isis_updated_date = isis_updated_date
            obj.status = status or obj.status
            obj.sps_pkg_name = sps_pkg_name or obj.sps_pkg_name
            obj.data = data or obj.data
            obj.save()
            logging.info("Created / Updated MigratedDocument {}".format(obj))
            return obj
        except Exception as e:
            raise exceptions.CreateOrUpdateMigratedDocumentError(
                _("Unable to create_or_update_migrated_document {} {} {} {} {}").format(
                    migrated_issue, pkg_name, pid, type(e), e
                )
            )

    @property
    def html_translations(self):
        """
        {
            "pt": {"before references": [], "after references": []},
            "es": {"before references": [], "after references": []},
        }
        """
        logging.info(f"html_translations: {self.migrated_issue} {self.pkg_name}")
        _html_texts = {}
        for html_file in MigratedFile.objects.filter(
            migrated_issue=self.migrated_issue,
            pkg_name=self.pkg_name,
            category="html",
        ).iterator():
            lang = html_file.lang.code2
            _html_texts.setdefault(lang, {})
            part = f"{html_file.part} references"
            _html_texts[lang][part] = html_file.text
        return _html_texts

    @property
    def xhtml_translations(self):
        """
        {
            "pt": {"before references": [], "after references": []},
            "es": {"before references": [], "after references": []},
        }
        """
        logging.info(f"xhtml_translations: {self.migrated_issue} {self.pkg_name}")
        xhtmls = {}
        for html_file in MigratedFile.objects.filter(
            migrated_issue=self.migrated_issue,
            pkg_name=self.pkg_name,
            category="xhtml",
        ).iterator():
            logging.info(f"get xhtml {html_file}")
            lang = html_file.lang.code2
            logging.info(f"lang={lang}")
            xhtmls.setdefault(lang, {})
            part = f"{html_file.part} references"
            xhtmls[lang][part] = html_file.text
            logging.info(xhtmls.keys())
        return xhtmls

    def html2xhtml(self):
        for html_file in MigratedFile.objects.filter(
            migrated_issue=self.migrated_issue,
            pkg_name=self.pkg_name,
            category="html",
        ).iterator():
            hc = HTMLContent(html_file.text)
            # FIXME
            logging.info(f"lang={html_file.lang.code2}")
            migrated_file = MigratedFile.create_or_update(
                migrated_issue=html_file.migrated_issue,
                file_content=hc.content,
                file_name=f"{html_file.pkg_name}-{html_file.lang.code2}-{html_file.part}.xhtml",
                category="xhtml",
                lang=html_file.lang.code2,
                part=html_file.part,
                pkg_name=html_file.pkg_name,
                creator=html_file.creator,
            )

    @property
    def translations(self):
        logging.info(f"translations: {self.xhtml_translations.keys()}")
        logging.info(len(self.xhtml_translations.items()))
        if not self.xhtml_translations:
            self.html2xhtml()
        return self.xhtml_translations

    @property
    def migrated_xml(self):
        for item in MigratedFile.objects.filter(
            migrated_issue=self.migrated_issue,
            pkg_name=self.pkg_name,
            category="xml",
        ).iterator():
            logging.info("found xml")
            return item

    @property
    def generated_xml(self):
        return GeneratedXMLFile.get(migrated_document=self)

    @property
    def xml_with_pre(self):
        logging.info("xml_with_pre...")
        if self.migrated_xml:
            logging.info("return migrated_xml.xml_with_pre")
            return self.migrated_xml.xml_with_pre
        if self.generated_xml:
            logging.info("return generated_xml.xml_with_pre")
            return self.generated_xml.xml_with_pre
        logging.info("Not found xml_with_pre")

    @property
    def sps_status(self):
        xml_status = None
        if self.file_type == "html":
            try:
                if self.generated_xml.status != choices.HTML2XML_DONE:
                    xml_status = choices.MS_XML_WIP
            except AttributeError:
                xml_status = choices.MS_XML_WIP

        if self.missing_assets:
            if xml_status:
                return choices.MS_XML_WIP_AND_MISSING_ASSETS
            return choices.MS_MISSING_ASSETS
        return choices.MS_IMPORTED

    @property
    def xml(self):
        if self.migrated_xml:
            return self.migrated_xml.file
        if self.generated_xml:
            return self.generated_xml.file


def body_and_back_directory_path(instance, filename):
    # file will be uploaded to MEDIA_ROOT/user_<id>/<filename>
    pid = instance.migrated_document.pid
    return (
        f"migration/{pid[1:10]}/"
        f"{pid[10:14]}/{pid[14:18]}/"
        f"{instance.migrated_document.pkg_name}/"
        f"body/"
        f"{instance.version}/{filename}"
    )


class BodyAndBackFile(CommonControlField):
    migrated_document = models.ForeignKey(
        "MigratedDocument", on_delete=models.SET_NULL, null=True, blank=True
    )
    file = models.FileField(
        upload_to=body_and_back_directory_path, null=True, blank=True
    )
    version = models.IntegerField()

    class Meta:
        indexes = [
            models.Index(fields=["migrated_document"]),
            models.Index(fields=["version"]),
        ]

    def __str__(self):
        return f"{self.migrated_document} {self.version}"

    def save_file(self, name, content):
        if self.file:
            try:
                with open(self.file.path, "rb") as fp:
                    c = fp.read()
                    if c == content:
                        logging.info("skip save file")
                        return
            except Exception as e:
                pass
        self.file.save(name, ContentFile(content))
        logging.info(f"Saved {self.file.path}")

    @classmethod
    def get(cls, migrated_document, version):
        logging.info(f"Get BodyAndBackFile {migrated_document} {version}")
        return cls.objects.get(
            migrated_document=migrated_document,
            version=version,
        )

    @classmethod
    def create_or_update(cls, migrated_document, version, file_content, creator):
        try:
            logging.info(
                f"Create or update BodyAndBackFile {migrated_document} {version}"
            )
            obj = cls.get(migrated_document, version)
            obj.updated_by = creator
            obj.updated = datetime.utcnow()
        except cls.DoesNotExist:
            obj = cls()
            obj.creator = creator
            obj.migrated_document = migrated_document

        try:
            obj.version = version
            obj.save()

            # cria / atualiza arquivo
            obj.save_file(obj.filename, file_content)
            obj.save()
            logging.info("Created {}".format(obj))
            return obj
        except Exception as e:
            raise exceptions.CreateOrUpdateBodyAndBackFileError(
                _("Unable to create_or_update_body and back file {} {} {} {}").format(
                    migrated_document, version, type(e), e
                )
            )

    @property
    def filename(self):
        return f"{now()}.xml"


def generated_xml_directory_path(instance, filename):
    pid = instance.migrated_document.pid
    return (
        f"migration/{pid[1:10]}/"
        f"{pid[10:14]}/{pid[14:18]}/"
        f"{instance.migrated_document.pkg_name}/"
        f"gen_xml/"
        f"{filename}"
    )


class GeneratedXMLFile(CommonControlField):
    migrated_document = models.ForeignKey(
        MigratedDocument, on_delete=models.SET_NULL, null=True, blank=True
    )
    file = models.FileField(
        upload_to=generated_xml_directory_path, null=True, blank=True
    )
    status = models.CharField(
        _("status"),
        max_length=25,
        choices=choices.HTML2XML_STATUS,
        default=choices.HTML2XML_NOT_EVALUATED,
    )

    class Meta:
        indexes = [
            models.Index(fields=["migrated_document"]),
        ]

    def __str__(self):
        return f"{self.migrated_document}"

    def save_file(self, name, content):
        if self.file:
            try:
                with open(self.file.path, "rb") as fp:
                    c = fp.read()
                    if c == content:
                        logging.info("skip save file")
                        return
            except Exception as e:
                pass
        self.file.save(name, ContentFile(content))
        logging.info(f"Saved {self.file.path}")

    @classmethod
    def get(cls, migrated_document):
        logging.info(f"Get GeneratedXMLFile {migrated_document}")
        return cls.objects.get(
            migrated_document=migrated_document,
        )

    @classmethod
    def create_or_update(cls, migrated_document, file_content, creator):
        try:
            logging.info(
                "Create or update GeneratedXMLFile {}".format(migrated_document)
            )
            obj = cls.get(migrated_document)
            obj.updated_by = creator
            obj.updated = datetime.utcnow()
        except cls.DoesNotExist:
            obj = cls()
            obj.creator = creator
            obj.migrated_document = migrated_document
        try:
            obj.save()

            # cria / atualiza arquivo
            obj.save_file(obj.filename, file_content)
            obj.save()
            logging.info("Created {}".format(obj))
            return obj
        except Exception as e:
            raise exceptions.CreateOrUpdateGeneratedXMLFileError(
                _("Unable to create_or_update_generated xml file {} {} {}").format(
                    migrated_document, type(e), e
                )
            )

    @property
    def filename(self):
        return f"{now()}.xml"

    @property
    def xml_with_pre(self):
        for item in XMLWithPre.create(path=self.file.path):
            return item
