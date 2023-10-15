import logging
import os
import sys
from datetime import datetime

from django.utils.translation import gettext_lazy as _

from collection.models import Collection
from core.controller import parse_yyyymmdd
from core.models import GlobalIncidentTracker
from issue.models import Issue, SciELOIssue
from journal.models import Journal, OfficialJournal, SciELOJournal
from package import choices as package_choices
from package.models import SPSPkg
from scielo_classic_website import classic_ws

from . import exceptions
from .choices import (
    DOC_GENERATED_SPS_PKG,
    DOC_TO_GENERATE_SPS_PKG,
    DOC_TO_GENERATE_XML,
    MS_IMPORTED,
    MS_TO_IGNORE,
    MS_TO_MIGRATE,
)
from .models import (
    ClassicWebsiteConfiguration,
    MigratedDocument,
    MigratedDocumentHTML,
    MigratedIssue,
    MigratedJournal,
)


def get_classic_website(collection_acron, user):
    try:
        logging.info(f"collection_acron={collection_acron}")
        config = ClassicWebsiteConfiguration.objects.get(
            collection__acron=collection_acron
        )
        return classic_ws.ClassicWebsite(
            bases_path=os.path.join(os.path.dirname(config.bases_work_path), "bases"),
            bases_work_path=config.bases_work_path,
            bases_translation_path=config.bases_translation_path,
            bases_pdf_path=config.bases_pdf_path,
            bases_xml_path=config.bases_xml_path,
            htdocs_img_revistas_path=config.htdocs_img_revistas_path,
            serial_path=config.serial_path,
            cisis_path=config.cisis_path,
            title_path=config.title_path,
            issue_path=config.issue_path,
        )
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        GlobalIncidentTracker.register_incident(
            collection_acron=collection_acron,
            app_name="migration",
            item_name="collection",
            item_id=collection_acron,
            message=None,
            context="get-classic-website-configuration",
            e=e,
            exc_traceback=exc_traceback,
            user=user,
        )


def migrate_title_db(
    user,
    collection,
    force_update=False,
):
    classic_website = get_classic_website(collection.acron, user)

    try:
        for (
            scielo_issn,
            journal_data,
        ) in classic_website.get_journals_pids_and_records():
            migrated_journal = create_or_update_migrated_journal_record(
                user,
                collection,
                scielo_issn,
                journal_data[0],
                force_update,
            )
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        GlobalIncidentTracker.register_incident(
            collection_acron=collection.acron,
            app_name="migration",
            item_name="journals",
            item_id=None,
            message=None,
            context="get_journals_pids_and_records",
            e=e,
            exc_traceback=exc_traceback,
            user=user,
        )


# def create_or_update_migrated_journal_record(
#     user,
#     collection,
#     scielo_issn,
#     journal_data,
#     force_update=False,
# ):
#     try:
#         migrated_journal = None

#         context = "get-data-from-classic-website"
#         classic_website_journal = classic_ws.Journal(journal_data)

#         context = "migrate-data"
#         migrated_journal = MigratedJournal.create_or_update(
#             collection=collection,
#             pid=scielo_issn,
#             user=user,
#             isis_created_date=classic_website_journal.isis_created_date,
#             isis_updated_date=classic_website_journal.isis_updated_date,
#             data=journal_data,
#             status=MS_TO_MIGRATE,
#             force_update=force_update,
#         )
#         migrated_journal.archive_incident_report()
#     except Exception as e:
#         exc_type, exc_value, exc_traceback = sys.exc_info()

#         try:
#             migrated_journal = MigratedJournal.get(
#                 collection=collection,
#                 pid=scielo_issn,
#             )
#             migrated_journal.add_incident(
#                 collection_acron=collection.acron,
#                 app_name="migration",
#                 user=user,
#                 context=context,
#                 item_name="journal",
#                 item_id=scielo_issn,
#                 e=e,
#                 message=None,
#                 exc_traceback=exc_traceback,
#             )
#         except MigratedJournal.DoesNotExist:
#             Incident.create(
#                 collection_acron=collection.acron,
#                 app_name="migration",
#                 item_name="journal",
#                 item_id=scielo_issn,
#                 message=None,
#                 context=context,
#                 e=e,
#                 exc_traceback=exc_traceback,
#                 creator=user,
#             )


def create_or_update_migrated_journal_record(
    user,
    collection,
    scielo_issn,
    journal_data,
    force_update=False,
):
    try:
        migrated_journal = None

        context = "get-data-from-classic-website"
        classic_website_journal = classic_ws.Journal(journal_data)

        context = "migrate-data"
        migrated_journal = MigratedJournal.create_or_update(
            collection=collection,
            pid=scielo_issn,
            user=user,
            isis_created_date=classic_website_journal.isis_created_date,
            isis_updated_date=classic_website_journal.isis_updated_date,
            data=journal_data,
            status=MS_TO_MIGRATE,
            force_update=force_update,
        )
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()

        if not migrated_journal:
            migrated_journal = MigratedJournal.create_or_update(
                collection=collection,
                pid=scielo_issn,
                user=user,
            )

        migrated_journal.add_incident(
            collection_acron=collection.acron,
            app_name="migration",
            user=user,
            context=context,
            item_name="journal",
            item_id=scielo_issn,
            e=e,
            message=None,
            exc_traceback=exc_traceback,
        )


def create_or_update_journal(
    user,
    migrated_journal,
    force_update,
):
    """
    Create/update OfficialJournal, SciELOJournal e Journal
    """
    try:
        collection = migrated_journal.collection
        journal_data = migrated_journal.data

        # obtém classic website journal
        classic_website_journal = classic_ws.Journal(journal_data)

        year, month, day = parse_yyyymmdd(classic_website_journal.first_year)
        official_journal = OfficialJournal.create_or_update(
            issn_electronic=classic_website_journal.electronic_issn,
            issn_print=classic_website_journal.print_issn,
            title=classic_website_journal.title,
            title_iso=classic_website_journal.title_iso,
            foundation_year=year,
            user=user,
        )
        journal = Journal.create_or_update(
            official_journal=official_journal,
        )
        # TODO
        # for publisher_name in classic_website_journal.raw_publisher_names:
        #     journal.add_publisher(user, publisher_name)

        scielo_journal = SciELOJournal.create_or_update(
            migrated_journal.collection,
            scielo_issn=migrated_journal.pid,
            creator=user,
            journal=journal,
            acron=classic_website_journal.acronym,
            title=classic_website_journal.title,
            availability_status=classic_website_journal.current_status,
        )
        migrated_journal.scielo_journal = scielo_journal
        migrated_journal.status = MS_IMPORTED
        migrated_journal.save()
        logging.info(f"Journal migration completed {migrated_journal}")
        return migrated_journal
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        message = _("Unable to create or update journal {}").format(migrated_journal)
        migrated_journal.add_incident(
            collection_acron=collection.acron,
            app_name="migration",
            user=user,
            context="create_or_update",
            item_name="journal",
            item_id=migrated_journal.pid,
            e=e,
            message=message,
            exc_traceback=exc_traceback,
        )


def migrate_issue_db(
    user,
    collection=None,
    force_update=False,
):
    """
    Migra os registros da base de dados issue
    """
    classic_website = get_classic_website(collection.acron, user)

    for issue_pid, issue_data in classic_website.get_issues_pids_and_records():
        migrated_issue = create_or_update_migrated_issue_record(
            user=user,
            collection=collection,
            scielo_issn=issue_pid[:9],
            issue_pid=issue_pid,
            issue_data=issue_data[0],
            force_update=force_update,
        )


def create_or_update_migrated_issue_record(
    user,
    collection,
    scielo_issn,
    issue_pid,
    issue_data,
    force_update=False,
):
    """
    Create/update MigratedIssue
    """
    try:
        migrated_issue = None

        classic_website_issue = classic_ws.Issue(issue_data)

        if classic_website_issue.is_press_release:
            status = MS_TO_IGNORE
        else:
            status = MS_TO_MIGRATE

        migrated_issue = MigratedIssue.create_or_update(
            collection=collection,
            pid=issue_pid,
            user=user,
            isis_created_date=classic_website_issue.isis_created_date,
            isis_updated_date=classic_website_issue.isis_updated_date,
            status=status,
            data=issue_data,
            force_update=force_update,
        )
        return migrated_issue
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()

        if not migrated_issue:
            migrated_issue = MigratedIssue.create_or_update(
                collection=collection,
                pid=issue_pid,
                user=user,
            )

        message = _("Unable to migrate issue {} {}").format(collection.acron, issue_pid)
        migrated_issue.add_incident(
            collection_acron=collection.acron,
            app_name="migration",
            user=user,
            context="migrate",
            item_name="issue",
            item_id=issue_pid,
            message=message,
            e=e,
            exc_traceback=exc_traceback,
        )


def create_or_update_issue(
    user,
    migrated_issue,
    force_update,
):
    """
    Create/update Issue e SciELOIssue
    """
    try:
        classic_website_issue = classic_ws.Issue(migrated_issue.data)
        scielo_journal = SciELOJournal.get(scielo_issn=classic_website_issue.journal)

        issue = Issue.get_or_create(
            journal=scielo_journal.journal,
            publication_year=classic_website_issue.publication_year,
            volume=classic_website_issue.volume,
            number=classic_website_issue.number,
            supplement=classic_website_issue.supplement,
            user=user,
        )
        scielo_issue = SciELOIssue.create_or_update(
            scielo_journal=scielo_journal,
            issue_pid=migrated_issue.pid,
            issue_folder=classic_website_issue.issue_label,
            issue=issue,
            user=user,
        )
        scielo_issue.publication_stage = None
        migrated_issue.scielo_issue = scielo_issue
        if migrated_issue.scielo_issue:
            migrated_issue.status = MS_IMPORTED
            migrated_issue.save()

        logging.info(f"Issue migration completed {migrated_issue}")
        return migrated_issue
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()

        message = _("Unable to create or update issue {} {}").format(
            migrated_issue.collection.acron, migrated_issue.pid
        )
        migrated_issue.add_incident(
            user=user,
            collection_acron=migrated_issue.collection.acron,
            app_name="migration",
            context="create_or_update",
            item_name="issue",
            item_id=migrated_issue.pid,
            e=e,
            message=message,
            exc_traceback=exc_traceback,
        )


class IssueMigration:
    def __init__(self, user, collection_acron, migrated_issue, force_update):
        self.classic_website = get_classic_website(collection_acron, user)
        self.collection_acron = collection_acron
        self.force_update = force_update
        self.migrated_issue = migrated_issue
        self.scielo_issue = self.migrated_issue.scielo_issue
        self.scielo_journal = self.scielo_issue.scielo_journal
        self.journal_acron = self.scielo_journal.acron
        self.user = user

    def _get_classic_website_rel_path(self, file_path):
        if "htdocs" in file_path:
            return file_path[file_path.find("htdocs") :]
        if "bases" in file_path:
            return file_path[file_path.find("bases") :]

    def check_category(self, file):
        if file["type"] == "pdf":
            check = file["name"]
            try:
                check = check.replace(file["lang"] + "_", "")
            except (KeyError, TypeError):
                pass
            try:
                check = check.replace(file["key"], "")
            except (KeyError, TypeError):
                pass
            if check == ".pdf":
                return "rendition"
            return "supplmat"
        return file["type"]

    def import_issue_files(self):
        """
        Migra os arquivos do fascículo (pdf, img, xml ou html)
        """
        classic_website_issue = classic_ws.Issue(self.migrated_issue.data)

        classic_issue_files = self.classic_website.get_issue_files(
            self.scielo_journal.acron,
            self.scielo_issue.issue_folder,
        )
        migrated = 0
        failure = 0
        for file in classic_issue_files:
            """
            {"type": "pdf", "key": name, "path": path, "name": basename, "lang": lang}
            {"type": "xml", "key": name, "path": path, "name": basename, }
            {"type": "html", "key": name, "path": path, "name": basename, "lang": lang, "part": label}
            {"type": "asset", "path": item, "name": os.path.basename(item)}
            """
            try:
                category = self.check_category(file)
                self.migrated_issue.add_file(
                    original_path=self._get_classic_website_rel_path(file["path"]),
                    source_path=file["path"],
                    category=category,
                    lang=file.get("lang"),
                    part=file.get("part"),
                    pkg_name=file.get("key"),
                    user=self.user,
                    force_update=self.force_update,
                )
                migrated += 1
            except Exception as e:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                failure += 1

                message = _("Unable to migrate issue files {} {}").format(
                    self.migrated_issue.collection.acron, file
                )
                self.migrated_issue.add_incident(
                    collection_acron=self.migrated_issue.collection.acron,
                    app_name="migration",
                    user=self.user,
                    context="migrate",
                    item_name="issue files",
                    item_id=self.migrated_issue.pid,
                    message=message,
                    e=e,
                    exc_traceback=exc_traceback,
                )

        self.migrated_issue.files_status = (
            MS_IMPORTED if failure == 0 else MS_TO_MIGRATE
        )
        self.migrated_issue.save()


def import_one_issue_files(
    user,
    migrated_issue,
    force_update,
):
    """
    Importa arquivos
    """
    try:

        migration = IssueMigration(
            user, migrated_issue.collection.acron, migrated_issue, force_update
        )

        # Melhor importar todos os arquivos e depois tratar da carga
        # dos metadados, e geração de XML, pois
        # há casos que os HTML mencionam arquivos de pastas diferentes
        # da sua pasta do fascículo
        migration.import_issue_files()
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()

        message = _("Unable to migrate issue {} {}").format(
            migrated_issue.collection.acron, migrated_issue.pid
        )
        migrated_issue.add_incident(
            collection_acron=migrated_issue.collection.acron,
            app_name="migration",
            user=user,
            context="migrate",
            item_name="files",
            item_id=migrated_issue.pid,
            message=message,
            e=e,
            exc_traceback=exc_traceback,
        )


def import_one_issue_document_records(
    user,
    migrated_issue,
    issue_folder=None,
    issue_pid=None,
    force_update=False,
):
    """
    Cria registros MigratedDocument com dados obtidos de base de dados ISIS
    de artigos
    """

    if migrated_issue.docs_status != MS_TO_MIGRATE:
        if not force_update:
            logging.warning(
                f"No document records will be migrated. {migrated_issue} "
                f"docs_status='{migrated_issue.docs_status}' and force_update=False"
            )
            return

    collection = migrated_issue.collection
    classic_website = get_classic_website(collection.acron, user)

    j = MigratedJournal.get(collection=collection, pid=migrated_issue.pid[:9])
    journal_issue_and_doc_data = {"title": j.data}
    journal_acron = j.scielo_journal.acron

    pids = set()
    pids_failed = set()
    for doc_id, doc_records in classic_website.get_documents_pids_and_records(
        journal_acron,
        issue_folder,
        migrated_issue.pid,
    ):
        try:
            migrated_document = None
            document_pid = None

            logging.info(f"Records: {doc_id} {issue_folder}")
            if len(doc_records) == 1:
                # é possível que em source_file_path exista registro tipo i

                journal_issue_and_doc_data["issue"] = doc_records[0]
                continue

            if not journal_issue_and_doc_data.get("issue"):
                journal_issue_and_doc_data["issue"] = migrated_issue.data

            journal_issue_and_doc_data["article"] = doc_records

            logging.info(f"records: {journal_issue_and_doc_data.keys()}")
            migrated_document = create_or_update_document_record(
                migrated_issue,
                journal_issue_and_doc_data,
                issue_pid,
                user,
                force_update,
                classic_website,
            )
            document_pid = migrated_document.pid[1:-5]
            if document_pid:
                pids.add(document_pid)
        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            if document_pid:
                pids.add(document_pid)
            message = _("Unable to migrate documents {} {} {} {}").format(
                collection.acron, journal_acron, issue_folder, doc_id
            )
            migrated_issue.add_incident(
                collection_acron=collection.acron,
                app_name="migration",
                user=user,
                item_name="document",
                item_id=f"{journal_acron} {issue_folder} {doc_id}",
                message=message,
                context="migrate",
                e=e,
                exc_traceback=exc_traceback,
            )
    # atualiza MigratedIssue.docs_status com MS_IMPORTED
    # for pid in pids:
    #     if pid in pids_failed:
    #         docs_status = MS_TO_MIGRATE
    #     else:
    #         docs_status = MS_IMPORTED
    #     MigratedIssue.objects.filter(
    #         collection=migrated_issue.collection,
    #         pid=pid,
    #     ).update(docs_status=docs_status)


def create_or_update_document_record(
    migrated_issue,
    journal_issue_and_doc_data,
    issue_pid,
    user,
    force_update,
    classic_website,
):
    try:
        migrated_document = None
        collection = migrated_issue.collection

        logging.info(
            f"OK Records.. {migrated_issue} {journal_issue_and_doc_data.keys()}"
        )

        # instancia Document com registros de title, issue e artigo
        classic_ws_doc = classic_ws.Document(journal_issue_and_doc_data)

        pid = classic_ws_doc.scielo_pid_v2 or (
            "S" + issue_pid + classic_ws_doc.order.zfill(5)
        )

        logging.info(f"Records.. {pid}")

        if len(pid) != 23:
            info = {
                "classic_ws_doc.scielo_pid_v2": classic_ws_doc.scielo_pid_v2,
                "order": classic_ws_doc.order,
                "issue_pid": issue_pid,
            }
            raise ValueError(
                f"Expected 23-characters pid. Found {pid} ({len(pid)}) {info}"
            )

        if classic_ws_doc.scielo_pid_v2 != pid:
            classic_ws_doc.scielo_pid_v2 = pid

        pid_, p_records = classic_website.get_p_records(pid)
        journal_issue_and_doc_data["article"].extend(p_records)
        if not journal_issue_and_doc_data["article"]:
            raise ValueError(f"Missing 'article' records for {pid}")

        # pkg_name
        pkg_name = classic_ws_doc.filename_without_extension
        if classic_ws_doc.file_type == "html":
            status = MS_TO_MIGRATE
            xml_status = DOC_TO_GENERATE_XML
            MigratedDocumentModel = MigratedDocumentHTML
        else:
            status = MS_IMPORTED
            xml_status = DOC_TO_GENERATE_SPS_PKG
            MigratedDocumentModel = MigratedDocument

        migrated_document = MigratedDocumentModel.create_or_update(
            collection,
            pid,
            migrated_issue,
            pkg_name=pkg_name,
            user=user,
            isis_created_date=classic_ws_doc.isis_created_date,
            isis_updated_date=classic_ws_doc.isis_updated_date,
            data=journal_issue_and_doc_data,
            status=MS_TO_MIGRATE,
            force_update=force_update,
        )
        migrated_document.xml_status = xml_status
        if classic_ws_doc.file_type == "html" and migrated_document.p_records:
            status = MS_IMPORTED
        migrated_document.status = status
        migrated_document.save()
        return migrated_document
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()

        message = _("Unable to migrate records {} {}").format(collection.acron, pid)
        if not migrated_document:
            migrated_document = MigratedDocumentModel.create_or_update(
                collection,
                pid,
                migrated_issue,
                pkg_name=pkg_name,
                user=user,
            )

        migrated_document.add_incident(
            collection_acron=collection.acron,
            app_name="migration",
            user=user,
            context="migrate",
            item_name="doc_records",
            item_id=f"{pid}",
            message=message,
            e=e,
            exc_traceback=exc_traceback,
        )
