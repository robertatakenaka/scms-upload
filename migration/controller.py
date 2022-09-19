import os
import logging
import traceback
import sys

from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model

from defusedxml.ElementTree import parse
from defusedxml.ElementTree import tostring as defusedxml_tostring

from packtools.sps.models.article_assets import (
    ArticleAssets,
    SupplementaryMaterials,
)
from packtools.sps.models.related_articles import (
    RelatedItems,
)
from packtools.sps.models.article_renditions import (
    ArticleRenditions,
)

# from scielo_classic_website import migration as classic_ws
from scielo_classic_website import classic_ws

from libs.dsm.files_storage.minio import MinioStorage
from libs.dsm.publication.db import mk_connection
from libs.dsm.publication.journals import JournalToPublish
from libs.dsm.publication.issues import IssueToPublish, get_bundle_id
from libs.dsm.publication.documents import DocumentToPublish

from collection.choices import CURRENT
from collection.controller import (
    JournalController,
    IssueController,
    DocumentController,
    get_scielo_journal_by_title,
    get_or_create_scielo_journal,
    get_scielo_issue_by_collection,
    get_classic_website_configuration,
)
from collection.exceptions import (
    GetSciELOJournalError,
)
from .models import (
    JournalMigration,
    IssueMigration,
    DocumentMigration,
    IssueFilesMigration,
    DocumentFilesMigration,
    MigrationFailure,
    SciELOFile,
    SciELOFileWithLang,
    SciELOHTMLFile,
    MigrationConfiguration,
)
from .choices import MS_MIGRATED, MS_PUBLISHED, MS_TO_IGNORE
from . import exceptions


User = get_user_model()
OPAC_STRING_CONNECTION = os.environ.get('OPAC_STRING_CONNECTION', 'mongodb://192.168.1.19:27017/scielo_qa')


def insert_hyphen_in_YYYYMMMDD(YYYYMMMDD):
    if YYYYMMMDD[4:6] == "00":
        return f"{YYYYMMMDD[:4]}"
    if YYYYMMMDD[6:] == "00":
        return f"{YYYYMMMDD[:4]}-{YYYYMMMDD[4:6]}"
    return f"{YYYYMMMDD[:4]}-{YYYYMMMDD[4:6]}-{YYYYMMMDD[6:]}"


def read_xml_file(file_path):
    return parse(file_path)


def tostring(xmltree):
    # garante que os diacríticos estarão devidamente representados
    return defusedxml_tostring(xmltree, encoding="utf-8").decod("utf-8")


def register_failure(collection_acron, action_name, object_name, pid, e,
                     exc_type, exc_value, exc_traceback, user_id):
    migration_failure = MigrationFailure()
    migration_failure.collection_acron = collection_acron
    migration_failure.action_name = action_name
    migration_failure.object_name = object_name
    migration_failure.pid = pid
    migration_failure.exception_msg = str(e)
    migration_failure.traceback = [
        str(item)
        for item in traceback.extract_tb(exc_traceback)
    ]
    migration_failure.exception_type = str(type(e))
    migration_failure.creator = User.objects.get(pk=user_id)
    migration_failure.save()


def get_migration_configuration(collection_acron):
    try:
        configuration = MigrationConfiguration.objects.get(
            classic_website_configuration__collection__acron=collection_acron)
    except Exception as e:
        raise exceptions.GetMigrationConfigurationError(
            _('Unable to get_migration_configuration {} {} {}').format(
                collection_acron, type(e), e
            )
        )
    return configuration


def get_or_create_journal_migration(scielo_journal, creator_id):
    """
    Returns a JournalMigration (registered or new)
    """
    try:
        jm, created = JournalMigration.objects.get_or_create(
            scielo_journal=scielo_journal,
            creator_id=creator_id,
        )
    except Exception as e:
        raise exceptions.GetOrCreateJournalMigrationError(
            _('Unable to get_or_create_journal_migration {} {} {}').format(
                scielo_journal, type(e), e
            )
        )
    return jm


# def migrate_and_publish_migrated_journals(
#         user_id, db_uri, source_file_path,
#         collection_acron,
#         force_update=False,
#         ):
#     mk_connection(db_uri)
#     for scielo_issn, journal_data in classic_ws.get_records_by_source_path("title", source_file_path):
#         try:
#             logging.info(_("Migrating journal {} {}").format(collection_acron, scielo_issn))
#             action = "migrate"
#             journal_migration = migrate_journal(
#                 user_id, collection_acron,
#                 scielo_issn, journal_data[0], force_update)
#             logging.info(_("Publish journal {}").format(journal_migration))
#             publish_migrated_journal(journal_migration)
#             logging.info(_("Migrated and published journal {}").format(journal_migration))
#         except Exception as e:
#             exc_type, exc_value, exc_traceback = sys.exc_info()
#             register_failure(
#                 collection_acron, action, "journal", scielo_issn, e,
#                 exc_type, exc_value, exc_traceback, user_id,
#             )


def migrate_journals(user_id,
                     collection_acron,
                     source_file_path=None,
                     force_update=False,
                     ):

    try:
        if not source_file_path:
            classic_website_configuration = get_classic_website_configuration(
                collection_acron)
            source_file_path = classic_website_configuration.title_path

        for scielo_issn, journal_data in classic_ws.get_records_by_source_path("title", source_file_path):
            try:
                logging.info(_("Migrating journal {} {}").format(collection_acron, scielo_issn))
                migrate_journal(user_id, collection_acron,
                                scielo_issn, journal_data[0], force_update)
            except Exception as e:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                register_failure(
                    collection_acron, "migrate", "journal", scielo_issn, e,
                    exc_type, exc_value, exc_traceback, user_id,
                )
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        register_failure(
            collection_acron, "migrate", "journal", "GENERAL", e,
            exc_type, exc_value, exc_traceback, user_id,
        )


def migrate_journal(user_id, collection_acron, scielo_issn, journal_data,
                    force_update=False):
    """
    Create/update JournalMigration
    """
    journal = classic_ws.Journal(journal_data)
    journal_controller = JournalController(
        user_id=user_id,
        collection_acron=collection_acron,
        scielo_issn=scielo_issn,
        issn_l=None,
        e_issn=journal.electronic_issn,
        print_issn=journal.print_issn,
        journal_acron=journal.acronym,
    )
    journal_migration = get_or_create_journal_migration(
        journal_controller.scielo_journal, creator_id=user_id)

    # check if it needs to be update
    if journal_migration.isis_updated_date == journal.isis_updated_date:
        if not force_update:
            # nao precisa atualizar
            return journal_migration
    try:
        journal_migration.isis_created_date = journal.isis_created_date
        journal_migration.isis_updated_date = journal.isis_updated_date
        journal_migration.status = MS_MIGRATED
        if journal.publication_status != CURRENT:
            journal_migration.status = MS_TO_IGNORE
        journal_migration.data = journal_data

        journal_migration.save()
        return journal_migration
    except Exception as e:
        raise exceptions.JournalMigrationSaveError(
            _("Unable to save journal migration {} {} {}").format(
                collection_acron, scielo_issn, e
            )
        )


def publish_migrated_journals(
        user_id,
        collection_acron,
        db_uri=None,
        ):

    try:
        if not db_uri:
            migration_configuration = get_migration_configuration(collection_acron)
            db_uri = migration_configuration.new_website_configuration.db_uri
    except Exception as e:
        db_uri = OPAC_STRING_CONNECTION

    try:
        mk_connection(db_uri or OPAC_STRING_CONNECTION)

        for journal_migration in JournalMigration.objects.filter(
                scielo_journal__collection__acron=collection_acron,
                scielo_journal__publication_status=CURRENT,
                status=MS_MIGRATED,
                ):

            try:
                logging.info(_("Publish journal {}").format(journal_migration))
                publish_migrated_journal(journal_migration)
            except Exception as e:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                register_failure(
                    collection_acron, "publication", "journal",
                    journal_migration.scielo_journal.scielo_issn, e,
                    exc_type, exc_value, exc_traceback, user_id,
                )

    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        register_failure(
            collection_acron, "publication", "journal",
            "GENERAL", e,
            exc_type, exc_value, exc_traceback, user_id,
        )


def publish_migrated_journal(journal_migration):
    journal = classic_ws.Journal(journal_migration.data)
    if journal.publication_status != CURRENT:
        # journal must not be published
        return

    if journal_migration.status != MS_MIGRATED:
        raise exceptions.JournalPublicationForbiddenError(
            _("For {}, it is expected JournalMigration.status == MS_MIGRATED. Found {}").format(
                journal_migration, journal_migration.status
            )
        )

    try:
        journal_to_publish = JournalToPublish(journal.scielo_issn)
        journal_to_publish.add_contact(
            " | ".join(journal.publisher_name),
            journal.publisher_email,
            ", ".join(journal.publisher_address),
            journal.publisher_city,
            journal.publisher_state,
            journal.publisher_country,
        )

        for mission in journal.mission:
            journal_to_publish.add_item_to_mission(
                mission["language"], mission["text"])

        for item in journal.status_history:
            journal_to_publish.add_item_to_timeline(
                item["status"],
                insert_hyphen_in_YYYYMMMDD(item["date"]),
                item.get("reason"),
            )
        journal_to_publish.add_journal_issns(
            journal.scielo_issn,
            journal.electronic_issn,
            journal.print_issn,
        )
        journal_to_publish.add_journal_titles(
            journal.title,
            journal.abbreviated_iso_title,
            journal.abbreviated_title,
        )

        journal_to_publish.add_online_submission_url(journal.submission_url)

        # TODO links previous e next
        # previous_journal = next_journal_title = None
        # if journal.previous_title:
        #     try:
        #         previous_journal = get_scielo_journal_by_title(
        #             journal.previous_title)
        #     except GetSciELOJournalError:
        #         previous_journal = None
        # if journal.next_title:
        #     try:
        #         next_journal = get_scielo_journal_by_title(journal.next_title)
        #         next_journal_title = journal.next_title
        #     except GetSciELOJournalError:
        #         next_journal_title = None
        # if previous_journal or next_journal_title:
        #     journal_to_publish.add_related_journals(
        #         previous_journal, next_journal_title,
        #     )
        for item in journal.sponsors:
            journal_to_publish.add_sponsor(item)

        # TODO confirmar se subject_categories é subject_descriptors
        journal_to_publish.add_thematic_scopes(
            journal.subject_descriptors, journal.subject_areas,
        )

        # journal não tem este dado
        # journal_to_publish.add_issue_count(
        #     journal.issue_count,
        # )

        # journal não tem este dado
        # journal_to_publish.add_item_to_metrics(
        #     journal.total_h5_index,
        #     journal.total_h5_median,
        #     journal.h5_metric_year,
        # )
        # journal não tem este dado
        # journal_to_publish.add_logo_url(journal.logo_url)
        journal_to_publish.add_acron(journal.acronym)
        journal_to_publish.publish_journal()
    except Exception as e:
        raise exceptions.PublishJournalError(
            _("Unable to publish {} {} {}").format(
                journal_migration, type(e), e)
        )

    try:
        journal_migration.status = MS_PUBLISHED
        journal_migration.save()
    except Exception as e:
        raise exceptions.PublishJournalError(
            _("Unable to publish {} {} {}").format(
                journal_migration, type(e), e)
        )


def get_or_create_issue_migration(scielo_issue, creator_id):
    """
    Returns a IssueMigration (registered or new)
    """
    try:
        jm, created = IssueMigration.objects.get_or_create(
            scielo_issue=scielo_issue,
            creator_id=creator_id,
        )
    except Exception as e:
        raise exceptions.GetOrCreateIssueMigrationError(
            _('Unable to get_or_create_issue_migration {} {} {}').format(
                scielo_issue, type(e), e
            )
        )
    return jm


def migrate_issues(
        user_id,
        collection_acron,
        source_file_path=None,
        force_update=False,
        ):

    try:
        if not source_file_path:
            classic_website_configuration = get_classic_website_configuration(
                collection_acron)
            source_file_path = classic_website_configuration.issue_path

        for issue_pid, issue_data in classic_ws.get_records_by_source_path("issue", source_file_path):
            try:
                migrate_issue(
                    user_id=user_id,
                    collection_acron=collection_acron,
                    scielo_issn=issue_pid[:9],
                    issue_pid=issue_pid,
                    issue_data=issue_data[0],
                    force_update=force_update,
                )
            except Exception as e:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                logging.exception(
                    "Error migrating issue %s %s %s %s " %
                    (issue_pid, exc_type, exc_value, exc_traceback)
                )
                register_failure(
                    collection_acron, "migrate", "issue", issue_pid, e,
                    exc_type, exc_value, exc_traceback, user_id,
                )
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        register_failure(
            collection_acron, "migrate", "issue", "GENERAL", e,
            exc_type, exc_value, exc_traceback, user_id,
        )
        return


def migrate_issue(
        user_id,
        collection_acron,
        scielo_issn,
        issue_pid,
        issue_data,
        force_update=False,
        ):
    """
    Create/update IssueMigration
    """
    logging.info(_("Migrating issue {} {}").format(collection_acron, issue_pid))
    issue = classic_ws.Issue(issue_data)

    issue_controller = IssueController(
        user_id=user_id,
        collection_acron=collection_acron,
        scielo_issn=scielo_issn,
        year=issue.publication_year,
        volume=issue.volume,
        number=issue.number,
        supplement=issue.suppl,
        issue_pid=issue_pid,
        is_press_release=issue.is_press_release,
    )

    logging.info(_("issue {}").format(issue_controller.scielo_issue))
    issue_migration = get_or_create_issue_migration(
        issue_controller.scielo_issue, creator_id=user_id)

    # check if it needs to be update
    if issue_migration.isis_updated_date == issue.isis_updated_date:
        if not force_update:
            # nao precisa atualizar
            logging.info("%s is up to date" % migration_id)
            return migration
    try:
        issue_migration.isis_created_date = issue.isis_created_date
        issue_migration.isis_updated_date = issue.isis_updated_date
        issue_migration.status = MS_MIGRATED
        if issue.is_press_release:
            issue_migration.status = MS_TO_IGNORE
        issue_migration.data = issue_data

        issue_migration.save()
        return issue_migration
    except Exception as e:
        raise exceptions.IssueMigrationSaveError(
            _("Unable to save {} migration {} {} {}").format(
                "issue", collection_acron, issue_pid, e
            )
        )


def publish_migrated_issues(
        user_id,
        collection_acron,
        db_uri=None,
        ):

    try:
        if not db_uri:
            migration_configuration = get_migration_configuration(collection_acron)
            db_uri = migration_configuration.new_website_configuration.db_uri
    except Exception as e:
        db_uri = OPAC_STRING_CONNECTION

    try:
        mk_connection(db_uri or OPAC_STRING_CONNECTION)

        for issue_migration in IssueMigration.objects.filter(
                scielo_issue__scielo_journal__collection__acron=collection_acron,
                status=MS_MIGRATED,
                ):

            try:
                logging.info(_("Publish issue {}").format(issue_migration))
                publish_migrated_issue(issue_migration)
            except Exception as e:
                raise e
                exc_type, exc_value, exc_traceback = sys.exc_info()
                register_failure(
                    collection_acron, "publication", "issue",
                    issue_migration.scielo_issue.issue_pid, e,
                    exc_type, exc_value, exc_traceback, user_id,
                )

    except Exception as e:
        raise e
        exc_type, exc_value, exc_traceback = sys.exc_info()
        register_failure(
            collection_acron, "publication", "issue",
            "GENERAL", e,
            exc_type, exc_value, exc_traceback, user_id,
        )


def publish_migrated_issue(issue_migration):
    """
    Raises
    ------
    PublishIssueError
    """
    issue = classic_ws.Issue(issue_migration.data)

    if issue_migration.status != MS_MIGRATED:
        raise exceptions.IssuePublicationForbiddenError(
            _("For {}, it is expected IssueMigration.status == MS_MIGRATED. Found {}").format(
                issue_migration, issue_migration.status
            )
        )
    try:
        published_id = get_bundle_id(
            issue.journal,
            issue.publication_year,
            issue.volume,
            issue.number,
            issue.supplement,
        )
        issue_to_publish = IssueToPublish(published_id)

        issue_to_publish.add_identification(
            issue.volume,
            issue.number,
            issue.supplement)
        issue_to_publish.add_journal(issue.journal)
        issue_to_publish.add_order(int(issue.order[4:]))
        issue_to_publish.add_pid(issue.pid)
        issue_to_publish.add_publication_date(
            issue.publication_year,
            issue.start_month,
            issue.end_month)
        # FIXME indica se há artigos / documentos
        issue_to_publish.has_docs = []

        issue_to_publish.publish_issue()
    except Exception as e:
        raise exceptions.PublishIssueError(
            _("Unable to publish {} {}").format(
                issue_migration.scielo_issue.issue_pid, e)
        )

    try:
        issue_migration.status = MS_PUBLISHED
        issue_migration.save()
    except Exception as e:
        raise exceptions.PublishIssueError(
            _("Unable to upate issue_migration status {} {}").format(
                issue_migration.scielo_issue.issue_pid, e)
        )


def get_files_storage(files_storage_config):
    try:
        return MinioStorage(
            minio_host=files_storage_config.host,
            minio_access_key=files_storage_config.access_key,
            minio_secret_key=files_storage_config.secret_key,
            bucket_root=files_storage_config.bucket_root,
            bucket_subdir=(
                files_storage_config.bucket_subdir or
                files_storage_config.bucket_public_subdir),
            minio_secure=True,
            minio_http_client=None,
        )
    except KeyError as e:
        raise exceptions.GetFilesStorageError(e)


def get_or_create_issue_files_migration(scielo_issue, creator_id):
    """
    Returns a IssueMigration (registered or new)
    """
    try:
        jm, created = IssueFilesMigration.objects.get_or_create(
            scielo_issue=scielo_issue,
            creator_id=creator_id,
        )
    except Exception as e:
        raise exceptions.GetOrCreateIssueFilesMigrationError(
            _('Unable to get_or_create_issue_files_migration {} {} {}').format(
                scielo_issue, type(e), e
            )
        )
    return jm


# def migrate_issues_files(
#         user_id,
#         collection_acron,
#         files_storage_config=None,
#         classic_ws_config=None,
#         ):

#     for issue_migration in IssueMigration.objects.filter(
#             scielo_issue__scielo_journal__collection__acron=collection_acron,
#             status=MS_MIGRATED,
#             ):
#         try:
#             issue_files_migration = migrate_issue_files(
#                 user_id=user_id,
#                 issue_migration=issue_migration,
#                 files_storage_config=files_storage_config,
#                 classic_ws_config=classic_ws_config,
#             )
#             logging.info(_("Migrated issue files {} {}").format(collection_acron, issue_files_migration))
#         except Exception as e:
#             exc_type, exc_value, exc_traceback = sys.exc_info()
#             register_failure(
#                 collection_acron, "migrate_files", "issue",
#                 issue_migration.scielo_issue.issue_pid, e,
#                 exc_type, exc_value, exc_traceback, user_id,
#             )


# def migrate_issue_files(
#         user_id,
#         issue_migration,
#         files_storage_config,
#         classic_ws_config,
#         ):
#     """
#     Create/update IssueFilesMigration
#     """
#     scielo_issue = issue_migration.scielo_issue
#     logging.info(_("Migrating issue files {} {}").format(scielo_issue, issue_migration))

#     issue_files_migration = get_or_create_issue_files_migration(
#         scielo_issue, creator_id=user_id)

#     if issue_files_migration.status == MS_PUBLISHED:
#         return issue_files_migration

#     try:
#         issue = classic_ws.Issue(issue_migration.data)
#         for item in store_issue_files(
#                 files_storage_config,
#                 scielo_issue.scielo_journal.acron,
#                 scielo_issue.issue_folder,
#                 classic_ws_config,
#                 ):
#             item['file_id'] = item.pop('key')

#             type = item.pop('type')
#             if type == "pdf":
#                 ClassFile = SciELOFileWithLang
#                 files = issue_files_migration.pdfs
#             elif type == "html":
#                 ClassFile = SciELOHTMLFile
#                 files = issue_files_migration.htmls
#             elif type == "xml":
#                 ClassFile = SciELOFile
#                 files = issue_files_migration.xmls
#             else:
#                 ClassFile = SciELOFile
#                 files = issue_files_migration.assets
#             files.add(ClassFile(**item))

#         issue_files_migration.status = MS_MIGRATED
#         issue_files_migration.save()
#         return issue_files_migration
#     except Exception as e:
#         raise exceptions.IssueFilesMigrationSaveError(
#             _("Unable to save issue files migration {} {}").format(
#                 scielo_issue, e)
#         )


# def store_issue_files(files_storage_config, journal_acron, issue_folder, classic_ws_config):
#     try:
#         issue_files = classic_ws.get_issue_files(journal_acron, issue_folder, classic_ws_config)
#     except Exception as e:
#         raise exceptions.IssueFilesStoreError(
#             _("Unable to issue files from classic website {} {} {}").format(
#                 journal_acron, issue_folder, e,
#             )
#         )
#     try:
#         files_storage = get_files_storage(files_storage_config)
#     except Exception as e:
#         raise exceptions.IssueFilesStoreError(
#             _("Unable to get files storage {} {} {} {}").format(
#                 files_storage_config, journal_acron, issue_folder, e,
#             )
#         )

#     for info in issue_files:
#         try:
#             logging.info(info)
#             name, ext = os.path.splitext(info['path'])
#             if ext in (".xml", ".html"):
#                 subdir = files_storage_config["migration"]
#             else:
#                 subdir = files_storage_config["publication"]
#             subdirs = os.path.join(
#                 subdir, journal_acron, issue_folder,
#             )
#             response = files_storage.register(
#                 info['path'], subdirs=subdirs, preserve_name=True)
#             info.update(response)
#             yield info

#         except Exception as e:
#             raise exceptions.IssueFilesStoreError(
#                 _("Unable to store issue files {} {} {}").format(
#                     journal_acron, issue_folder, e,
#                 )
#             )
