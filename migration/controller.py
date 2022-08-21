import os

from libs.dsm.classic_ws import classic_ws
from libs.dsm.publication.journals import JournalToPublish
from libs.dsm.publication.issues import IssueToPublish, get_bundle_id
from libs.dsm.publication.documents import DocumentToPublish
from libs.dsm.publication import db
from libs.dsm.publication.exceptions import (
    PublishJournalError,
    PublishIssueError,
    PublishDocumentError,
    JournalPublicationForbiddenError,
    IssuePublicationForbiddenError,
    DocumentPublicationForbiddenError,
)
from libs.dsm.files_storage.minio import MinioStorage
from .models import (
    JournalMigrationTracker, MigratedJournal,
    IssueMigration, IssueFilesMigration,
    DocumentMigrationTracker, MigratedDocument,
)
from .choices import MS_MIGRATED, MS_PUBLISHED
from .exceptions import (
    JournalMigrationTrackSaveError,
    MigratedJournalSaveError,
    IssueMigrationTrackSaveError,
    MigratedIssueSaveError,
    IssueFilesMigrationGetError,
    IssueFilesMigrationSaveError,
    DocumentMigrationTrackSaveError,
    MigratedDocumentSaveError,
)


def connect(connection):
    host = connection.get("host")
    alias = connection.get("alias")
    return db.mk_connection(host, alias=alias)


def get_classic_website_records(db_type, source_file_path):
    return classic_ws.get_records_by_source_path(db_type, source_file_path)


def get_migrated_journal(**kwargs):
    try:
        j = MigratedJournal.objects.get(**kwargs)
    except MigratedJournal.DoesNotExist:
        j = MigratedJournal()
    return j


def get_journal_migration_tracker(**kwargs):
    try:
        j = JournalMigrationTracker.objects.get(**kwargs)
    except JournalMigrationTracker.DoesNotExist:
        j = JournalMigrationTracker()
    return j


def migrate_journal(journal_id, data, force_update=False):
    """
    Create/update MigratedJournal e JournalMigrationTracker

    """
    journal_migration = get_journal_migration_tracker(scielo_issn=journal_id)
    classic_ws_j = classic_ws.Journal(data)

    if not force_update:
        # check if it needs to be update
        if journal_migration.isis_updated_date == classic_ws_j.isis_updated_date:
            # nao precisa atualizar
            return

    try:
        migrated = get_migrated_journal(scielo_issn=journal_id)
        migrated.scielo_issn = journal_id
        migrated.acron = classic_ws_j.acron
        migrated.title = classic_ws_j.title
        migrated.record = data
        migrated.save()
    except Exception as e:
        raise MigratedJournalSaveError(
            "Unable to save migrated journal %s %s" %
            (journal_id, e)
        )

    try:
        journal_migration.acron = classic_ws_j.acron
        journal_migration.isis_created_date = classic_ws_j.isis_created_date
        journal_migration.isis_updated_date = classic_ws_j.isis_updated_date
        journal_migration.status = MS_MIGRATED
        journal_migration.journal = migrated

        journal_migration.save()
    except Exception as e:
        raise JournalMigrationTrackSaveError(
            "Unable to save journal migration track %s %s" %
            (journal_id, e)
        )


def publish_journal(journal_id):
    """
    Raises
    ------
    PublishJournalError
    """
    try:
        journal_migration = JournalMigrationTracker.objects.get(
            scielo_issn=journal_id)
    except JournalMigrationTracker.DoesNotExist as e:
        raise PublishJournalError(
            "JournalMigrationTracker does not exists %s %s" % (journal_id, e))

    if journal_migration.status != MS_MIGRATED:
        raise JournalPublicationForbiddenError(
            "JournalMigrationTracker.status of %s is not MS_MIGRATED" %
            journal_id
        )

    try:
        classic_ws_j = classic_ws.Journal(journal_migration.journal.record)

        journal_to_publish = JournalToPublish(journal_id)

        journal_to_publish.add_contact(
            classic_ws_j.publisher_name,
            classic_ws_j.publisher_email,
            classic_ws_j.publisher_address,
            classic_ws_j.publisher_city,
            classic_ws_j.publisher_state,
            classic_ws_j.publisher_country,
        )
        for lang, text in classic_ws_j.mission.items():
            journal_to_publish.add_item_to_mission(lang, text)

        for item in classic_ws_j.status_history:
            journal_to_publish.add_item_to_timeline(
                item["status"], item["since"], item["reason"],
            )
        journal_to_publish.add_journal_issns(
            classic_ws_j.scielo_issn,
            classic_ws_j.electronic_issn,
            classic_ws_j.print_issn,
        )
        journal_to_publish.add_journal_titles(
            classic_ws_j.title,
            classic_ws_j.abbreviated_iso_title,
            classic_ws_j.abbreviated_title,
        )

        journal_to_publish.add_online_submission_url(classic_ws_j.submission_url)

        previous_journal = next_journal_title = None
        if classic_ws_j.previous_title:
            previous_journal = get_migrated_journal(
                title=classic_ws_j.previous_title)
            if not previous_journal.scielo_issn:
                previous_journal = None
        if classic_ws_j.next_title:
            next_journal = get_migrated_journal(title=classic_ws_j.next_title)
            if next_journal.scielo_issn:
                next_journal_title = classic_ws_j.next_title
        if previous_journal or next_journal_title:
            journal_to_publish.add_related_journals(
                previous_journal, next_journal_title,
            )
        for item in classic_ws_j.sponsors:
            journal_to_publish.add_sponsor(item)

        # TODO confirmar se subject_categories é subject_descriptors
        journal_to_publish.add_thematic_scopes(
            classic_ws_j.subject_descriptors, classic_ws_j.subject_areas,
        )

        # classic_ws_j não tem este dado
        # journal_to_publish.add_issue_count(
        #     classic_ws_j.issue_count,
        # )

        # classic_ws_j não tem este dado
        # journal_to_publish.add_item_to_metrics(
        #     classic_ws_j.total_h5_index,
        #     classic_ws_j.total_h5_median,
        #     classic_ws_j.h5_metric_year,
        # )
        # classic_ws_j não tem este dado
        # journal_to_publish.add_logo_url(classic_ws_j.logo_url)

        journal_to_publish.publish_journal()
    except Exception as e:
        raise PublishJournalError(
            "Unable to publish %s %s" % (journal_id, e)
        )

    try:
        journal_migration.status = MS_PUBLISHED
        journal_migration.save()
    except Exception as e:
        raise PublishJournalError(
            "Unable to upate journal_migration status %s %s" % (journal_id, e)
        )


##################################################################
# ISSUE

def get_issue_migration(**kwargs):
    try:
        j = IssueMigration.objects.get(**kwargs)
    except IssueMigration.DoesNotExist:
        j = IssueMigration()
    return j


def migrate_issue(issue_pid, data, force_update=False):
    """
    Create/update MigratedIssue e IssueMigration

    """
    issue_migration = get_issue_migration(issue_pid=issue_pid)
    classic_ws_i = classic_ws.Issue(data)

    if not force_update:
        # check if it needs to be update
        if issue_migration.isis_updated_date == classic_ws_i.isis_updated_date:
            # nao precisa atualizar
            return

    try:
        issue_migration.issue_pid = classic_ws_i.issue_pid
        issue_migration.acron = classic_ws_i.acron
        issue_migration.scielo_issn = classic_ws_i.scielo_issn
        issue_migration.year = classic_ws_i.year
        issue_migration.isis_created_date = classic_ws_i.isis_created_date
        issue_migration.isis_updated_date = classic_ws_i.isis_updated_date
        issue_migration.status = MS_MIGRATED
        issue_migration.record = data

        issue_migration.save()
    except Exception as e:
        raise MigratedIssueSaveError(
            "Unable to save issue migration track %s %s" %
            (issue_pid, e)
        )


def publish_issue(issue_pid):
    """
    Raises
    ------
    PublishIssueError
    """
    try:
        issue_migration = IssueMigration.objects.get(
            pid=issue_pid)
    except IssueMigration.DoesNotExist as e:
        raise PublishIssueError(
            "IssueMigration does not exists %s %s" % (issue_pid, e))

    if issue_migration.status != MS_MIGRATED:
        raise IssuePublicationForbiddenError(
            "IssueMigration.status of %s is not MS_MIGRATED" %
            issue_pid
        )

    try:
        classic_ws_i = classic_ws.Issue(issue_migration.record)
        published_id = get_bundle_id(
            classic_ws_i.journal,
            classic_ws_i.year,
            classic_ws_i.volume,
            classic_ws_i.number,
            classic_ws_i.supplement,
        )
        issue_to_publish = IssueToPublish(published_id)

        issue_to_publish.add_identification(
            classic_ws_i.volume,
            classic_ws_i.number,
            classic_ws_i.supplement)
        issue_to_publish.add_journal(classic_ws_i.journal)
        issue_to_publish.add_order(int(classic_ws_i.order[4:]))
        issue_to_publish.add_pid(classic_ws_i.pid)
        issue_to_publish.add_publication_date(
            classic_ws_i.year,
            classic_ws_i.start_month,
            classic_ws_i.end_month)
        issue_to_publish.has_docs = []

        issue_to_publish.publish_issue()
    except Exception as e:
        raise PublishIssueError(
            "Unable to publish %s %s" % (issue_pid, e)
        )

    try:
        issue_migration.status = MS_PUBLISHED
        issue_migration.save()
    except Exception as e:
        raise PublishIssueError(
            "Unable to upate issue_migration status %s %s" % (issue_pid, e)
        )


###############################################################################
def get_issue_files_migration(**kwargs):
    try:
        j = IssueFilesMigration.objects.get(**kwargs)
    except IssueFilesMigration.DoesNotExist:
        j = IssueFilesMigration()
    return j


def migrate_issue_files(issue_pid, files_storage, force_update=False):
    """
    Create/update MigratedIssue e IssueMigration

    """
    issue_files_migration = get_issue_files_migration(issue_pid=issue_pid)
    if issue_files_migration.status == MS_PUBLISHED and not force_update:
        return

    issue_migration = get_issue_migration(issue_pid=issue_pid)
    if not issue_migration.record:
        raise IssueFilesMigrationGetError(
            "Unable to get issue migration data %s" %
            issue_pid
        )

    try:
        classic_ws_i = classic_ws.Issue(issue_migration.record)
        classic_website_files = classic_ws.get_issue_files(
            classic_ws_i.acron, classic_ws_i.issue_label)
    except Exception as e:
        raise IssueFilesMigrationGetError(
            "Unable to get issue files %s %s" %
            (issue_pid, e)
        )

    try:
        paths = {}
        for file_path in classic_website_files['paths']:
            subdirs = os.path.join(
                "public", classic_ws_i.acron, classic_ws_i.issue_label,
            )
            paths[os.path.basename(file_path)] = files_storage.register(
                file_path, subdirs=subdirs, preserve_name=True)

        issue_files_migration.paths = paths
    except Exception as e:
        raise IssueFilesMigrationSaveError(
            "Unable to register issue files %s %s" %
            (issue_pid, e)
        )

    try:
        issue_files_migration.info = classic_website_files["info"]

        issue_files_migration.issue_pid = classic_ws_i.issue_pid
        issue_files_migration.acron = classic_ws_i.acron
        issue_files_migration.issue_folder = classic_ws_i.issue_label
        issue_files_migration.status = MS_PUBLISHED

        issue_files_migration.save()
    except Exception as e:
        raise IssueFilesMigrationSaveError(
            "Unable to save issue files migration %s %s" %
            (issue_pid, e)
        )


###############################################################################
def get_migrated_doc(**kwargs):
    try:
        j = MigratedDocument.objects.get(**kwargs)
    except MigratedDocument.DoesNotExist:
        j = MigratedDocument()
    return j


def get_doc_migration_tracker(**kwargs):
    try:
        j = DocumentMigrationTracker.objects.get(**kwargs)
    except DocumentMigrationTracker.DoesNotExist:
        j = DocumentMigrationTracker()
    return j


def migrate_document(pid, data, force_update=False):
    """
    Create/update MigratedDocument e DocumentMigrationTracker

    """
    doc_migration = get_doc_migration_tracker(pid=pid)
    classic_ws_doc = classic_ws.Document(data)

    if not force_update:
        # check if it needs to be update
        if doc_migration.isis_updated_date == classic_ws_doc.isis_updated_date:
            # nao precisa atualizar
            return
    try:
        migrated = get_migrated_doc(pid=pid)
        migrated.pid = pid
        migrated.record = data
        migrated.save()
    except Exception as e:
        raise MigratedDocumentSaveError(
            "Unable to save migrated document %s %s" %
            (pid, e)
        )

    try:
        doc_migration.pid = classic_ws_doc.pid
        doc_migration.acron = classic_ws_doc.acron
        doc_migration.scielo_issn = classic_ws_doc.scielo_issn
        doc_migration.year = classic_ws_doc.year
        doc_migration.isis_created_date = classic_ws_doc.isis_created_date
        doc_migration.isis_updated_date = classic_ws_doc.isis_updated_date
        doc_migration.status = MS_MIGRATED
        doc_migration.migrated_doc = migrated

        doc_migration.save()
    except Exception as e:
        raise DocumentMigrationTrackSaveError(
            "Unable to save document migration track %s %s" %
            (pid, e)
        )


def publish_document(pid):
    """
    Raises
    ------
    PublishDocumentError
    """
    try:
        doc_migration = DocumentMigrationTracker.objects.get(pid=pid)
    except DocumentMigrationTracker.DoesNotExist as e:
        raise PublishDocumentError(
            "DocumentMigrationTracker does not exists %s %s" % (pid, e))

    if doc_migration.status != MS_MIGRATED:
        raise DocumentPublicationForbiddenError(
            "DocumentMigrationTracker.status of %s is not MS_MIGRATED" %
            pid
        )

    try:
        classic_ws_doc = classic_ws.Document(
            doc_migration.migrated_doc.records)
        # TODO
        v3 = "xxxxx"
        doc_to_publish = DocumentToPublish(v3)

        # IDS
        doc_to_publish.add_identifiers(
            classic_ws_doc.scielo_pid_v2,
            classic_ws_doc.publisher_ahead_id,
        )

        # MAIN METADATA
        doc_to_publish.add_document_type(classic_ws_doc.document_type)
        doc_to_publish.add_main_metadata(
            classic_ws_doc.title,
            classic_ws_doc.section,
            classic_ws_doc.abstract,
            classic_ws_doc.lang,
            classic_ws_doc.doi,
        )
        for item in classic_ws_doc.authors:
            doc_to_publish.add_author_meta(
                item['surname'], item['given_names'],
                item.get("suffix"),
                item.get("affiliation"),
                item.get("orcid"),
            )

        # ISSUE
        year = classic_ws_doc.document_publication_date[:4]
        month = classic_ws_doc.document_publication_date[4:6]
        day = classic_ws_doc.document_publication_date[6:]
        doc_to_publish.add_publication_date(year, month, day)

        doc_to_publish.add_in_issue(
            classic_ws_doc.order,
            classic_ws_doc.fpage,
            classic_ws_doc.fpage_seq,
            classic_ws_doc.lpage,
            classic_ws_doc.elocation,
        )

        # ISSUE
        bundle_id = get_bundle_id(
            classic_ws_doc.journal,
            classic_ws_doc.year,
            classic_ws_doc.volume,
            classic_ws_doc.number,
            classic_ws_doc.supplement,
        )
        doc_to_publish.add_issue(bundle_id)

        # JOURNAL
        doc_to_publish.add_journal(classic_ws_doc.journal)

        # IDIOMAS
        for item in classic_ws_doc.doi_with_lang:
            doc_to_publish.add_doi_with_lang(item["language"], item["doi"])

        for item in classic_ws_doc.abstracts:
            doc_to_publish.add_abstract(item['language'], item['text'])

        for item in classic_ws_doc.translated_sections:
            doc_to_publish.add_section(item['language'], item['text'])

        for item in classic_ws_doc.translated_titles:
            doc_to_publish.add_translated_titles(
                item['language'], item['text'],
            )
        for lang, keywords in classic_ws_doc.keywords_groups.items():
            doc_to_publish.add_keywords(lang, keywords)

        # ARQUIVOS
        # doc_to_publish.add_xml(xml)
        # for item in classic_ws_doc.htmls:
        #     doc_to_publish.add_html(language, uri)
        # for item in classic_ws_doc.mat_suppl_items:
        #     doc_to_publish.add_mat_suppl(lang, url, ref_id, filename)
        # for item in classic_ws_doc.pdf:
        #     doc_to_publish.add_pdf(lang, url, filename, type)

        # RELATED
        # doc_to_publish.add_related_article(doi, ref_id, related_type)

        doc_to_publish.publish_document()
    except Exception as e:
        raise PublishDocumentError(
            "Unable to publish %s %s" % (pid, e)
        )

    try:
        doc_migration.status = MS_PUBLISHED
        doc_migration.save()
    except Exception as e:
        raise PublishDocumentError(
            "Unable to upate doc_migration status %s %s" % (pid, e)
        )
