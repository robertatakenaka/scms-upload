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
    DocumentFilesMigrationGetError,
)
from .models import (
    JournalMigration,
    IssueMigration, IssueFilesMigration,
    DocumentMigration,
    DocumentFilesMigration,
)
from .choices import MS_MIGRATED, MS_PUBLISHED
from .exceptions import (
    JournalMigrationSaveError,
    IssueMigrationSaveError,
    IssueFilesMigrationGetError,
    IssueFilesMigrationSaveError,
    DocumentMigrationSaveError,
    DocumentFilesMigrationSaveError,
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


def get_journal_migration(**kwargs):
    try:
        j = JournalMigration.objects.get(**kwargs)
    except JournalMigration.DoesNotExist:
        j = JournalMigration()
    return j


def migrate_journal(journal_id, data, force_update=False):
    """
    Create/update MigratedJournal e JournalMigration

    """
    journal_migration = get_journal_migration(scielo_issn=journal_id)
    classic_ws_j = classic_ws.Journal(data)

    # check if it needs to be update
    if journal_migration.isis_updated_date == classic_ws_j.isis_updated_date:
        if not force_update:
            # nao precisa atualizar
            return

    try:
        journal_migration.title = classic_ws_j.title
        journal_migration.acron = classic_ws_j.acron
        journal_migration.isis_created_date = classic_ws_j.isis_created_date
        journal_migration.isis_updated_date = classic_ws_j.isis_updated_date
        journal_migration.status = MS_MIGRATED
        journal_migration.record = data

        journal_migration.save()
    except Exception as e:
        raise JournalMigrationSaveError(
            "Unable to save journal migration %s %s" %
            (journal_id, e)
        )


def publish_journal(journal_id):
    """
    Raises
    ------
    PublishJournalError
    """
    try:
        journal_migration = JournalMigration.objects.get(
            scielo_issn=journal_id)
    except JournalMigration.DoesNotExist as e:
        raise PublishJournalError(
            "JournalMigration does not exists %s %s" % (journal_id, e))

    if journal_migration.status != MS_MIGRATED:
        raise JournalPublicationForbiddenError(
            "JournalMigration.status of %s is not MS_MIGRATED" %
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
        raise IssueMigrationSaveError(
            "Unable to save issue migration %s %s" %
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


def migrate_issue_files(issue_pid, record, files_storage, force_update=False):
    """
    Create/update MigratedIssue e IssueMigration

    """
    issue_files_migration = get_issue_files_migration(issue_pid=issue_pid)
    if issue_files_migration.status == MS_PUBLISHED and not force_update:
        return

    try:
        classic_ws_i = classic_ws.Issue(record)
        acron = classic_ws_i.acron
        issue_folder = classic_ws_i.issue_label
        classic_website_files = classic_ws.get_issue_files(acron, issue_folder)
    except Exception as e:
        raise IssueFilesMigrationGetError(
            "Unable to get issue files %s %s" %
            (issue_pid, e)
        )

    try:
        groups = dict(
            xml=XMLIssueFiles(),
            pdf=PDFIssueFiles(),
            html=HTMLIssueFiles(),
            asset=AssetIssueFiles(),
        )
        for info in classic_website_files:
            subdirs = os.path.join(
                "public", acron, issue_folder,
            )
            info['uri'] = files_storage.register(
                info['path'], subdirs=subdirs, preserve_name=True)
            _set_info(groups, **info)

    except Exception as e:
        raise IssueFilesMigrationSaveError(
            "Unable to register issue files %s %s" %
            (issue_pid, e)
        )

    try:
        issue_files_migration.xmls = groups.get("xml").items
        issue_files_migration.htmls = groups.get("html").items
        issue_files_migration.pdfs = groups.get("pdf").items
        issue_files_migration.assets = groups.get("asset").items

        issue_files_migration.issue_pid = classic_ws_i.issue_pid
        issue_files_migration.acron = acron
        issue_files_migration.issue_folder = issue_folder
        issue_files_migration.status = MS_MIGRATED

        issue_files_migration.save()
    except Exception as e:
        raise IssueFilesMigrationSaveError(
            "Unable to save issue files migration %s %s" %
            (issue_pid, e)
        )


def _set_info(groups, type_, uri, name, key=None, lang=None, part=None):
    kwargs = {}
    if key:
        kwargs['key'] = key
    if lang:
        kwargs['lang'] = lang
    if part:
        kwargs['part'] = part
    if uri:
        kwargs['uri'] = uri
    if name:
        kwargs['name'] = name
    groups[type_].add_item(**kwargs)


###############################################################################
def get_doc_files_migration(**kwargs):
    try:
        j = DocumentFilesMigration.objects.get(**kwargs)
    except DocumentFilesMigration.DoesNotExist:
        j = DocumentFilesMigration()
    return j


def migrate_document_files(pid, data, force_update=False):
    """
    Create/update DocumentMigration

    """
    doc_files_migration = get_doc_files_migration(pid=pid)

    # check if it needs to be update
    if doc_files_migration.status == MS_MIGRATED:
        if not force_update:
            # nao precisa atualizar
            return

    try:
        classic_ws_doc = classic_ws.Document(data)
        issue_files_migration = get_issue_files_migration(
            acron=classic_ws_doc.acron,
            issue_folder=classic_ws_doc.issue_label,
        )
        if issue_files_migration.status != MS_MIGRATED:
            raise DocumentFilesMigrationGetError(
                "Unable to get issue files migration %s %s" %
                (classic_ws_doc.acron, classic_ws_doc.issue_label)
            )
    except Exception as e:
        raise DocumentFilesMigrationGetError(
            "Unable to get issue files migration %s %s" %
            (classic_ws_doc.acron, classic_ws_doc.issue_label)
        )

    try:
        doc_files_migration.pid = classic_ws_doc.pid
        doc_files_migration.acron = classic_ws_doc.acron
        doc_files_migration.issue_folder = classic_ws_doc.issue_label
        doc_files_migration.status = MS_MIGRATED
        doc_files_migration.filename_without_extension = classic_ws_doc.filename_without_extension

        key = classic_ws_doc.filename_without_extension
        text_langs = issue_files_migration.htmls.get_langs(key) or []
        doc_files_migration.text_langs = (
            [{"lang": classic_ws_doc.original_language}] +
            text_langs
        )
        doc_files_migration.pdfs = issue_files_migration.pdfs.get_list(key)

        # doc_files_migration.xmls = todo
        # doc_files_migration.assets = todo

        doc_files_migration.save()
    except Exception as e:
        raise DocumentFilesMigrationSaveError(
            "Unable to save document migration %s %s" %
            (pid, e)
        )


###############################################################################
def get_doc_migration(**kwargs):
    try:
        j = DocumentMigration.objects.get(**kwargs)
    except DocumentMigration.DoesNotExist:
        j = DocumentMigration()
    return j


def migrate_document(pid, data, force_update=False):
    """
    Create/update DocumentMigration

    """
    doc_migration = get_doc_migration(pid=pid)
    classic_ws_doc = classic_ws.Document(data)

    if not force_update:
        # check if it needs to be update
        if doc_migration.isis_updated_date == classic_ws_doc.isis_updated_date:
            # nao precisa atualizar
            return
    try:
        doc_migration.pid = classic_ws_doc.pid
        doc_migration.acron = classic_ws_doc.acron
        doc_migration.scielo_issn = classic_ws_doc.scielo_issn
        doc_migration.year = classic_ws_doc.year
        doc_migration.isis_created_date = classic_ws_doc.isis_created_date
        doc_migration.isis_updated_date = classic_ws_doc.isis_updated_date
        doc_migration.status = MS_MIGRATED
        doc_migration.records = data

        doc_migration.save()
    except Exception as e:
        raise DocumentMigrationSaveError(
            "Unable to save document migration %s %s" %
            (pid, e)
        )


def publish_document(pid):
    """
    Raises
    ------
    PublishDocumentError
    """
    try:
        doc_migration = DocumentMigration.objects.get(pid=pid)
    except DocumentMigration.DoesNotExist as e:
        raise PublishDocumentError(
            "DocumentMigration does not exists %s %s" % (pid, e))

    if doc_migration.status != MS_MIGRATED:
        raise DocumentPublicationForbiddenError(
            "DocumentMigration.status of %s is not MS_MIGRATED" %
            pid
        )

    try:
        doc_files_migration = DocumentFilesMigration.objects.get(pid=pid)
    except DocumentFilesMigration.DoesNotExist as e:
        raise PublishDocumentError(
            "DocumentFilesMigration does not exists %s %s" % (pid, e))

    if doc_files_migration.status != MS_MIGRATED:
        raise DocumentPublicationForbiddenError(
            "DocumentFilesMigration.status of %s is not MS_MIGRATED" %
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
        for item in doc_files_migration.htmls:
            doc_to_publish.add_html(item["lang"], item.get("uri"))
        # for item in classic_ws_doc.mat_suppl_items:
        #     doc_to_publish.add_mat_suppl(lang, url, ref_id, filename)
        for item in doc_files_migration.pdfs:
            doc_to_publish.add_pdf(**item)

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

############################################################################

class PDFIssueFiles:
    def __init__(self, items=None):
        self.items = items

    def add_item(self, key, lang, name, uri):
        if not self.items:
            self.items = {}
            self.items.setdefault(key, {})
        self.items[key][lang] = {
            "name": name,
            "uri": uri,
        }

    def get_item(self, key, lang):
        return self.items[key][lang]

    def get_list(self, key):
        items = []
        for lang, name_and_uri in self.items[key]:
            items.append(
                {"lang": lang, "url": name_and_uri['uri'],
                 "filename": name_and_uri['name'], "type": "pdf"})
        return items


class XMLIssueFiles:
    def __init__(self, items=None):
        self.items = items

    def add_item(self, key, name, uri):
        if not self.items:
            self.items = {}
            self.items.setdefault(key, {})
        self.items[key] = {
            "name": name,
            "uri": uri,
        }

    def get_item(self, key):
        return self.items[key]


class AssetIssueFiles:
    def __init__(self, items=None):
        self.items = items

    def add_item(self, name, uri):
        if not self.items:
            self.items = {}
        self.items[name] = uri

    def get_item(self, name):
        return self.items[name]


class HTMLIssueFiles:
    def __init__(self, items=None):
        self.items = items

    def add_item(self, key, lang, name, uri, part):
        if not self.items:
            self.items = {}
            self.items.setdefault(key, {})
        self.items[key][lang].setdefault(part, {})
        self.items[key][lang][part] = {
            "name": name,
            "uri": uri,
        }

    def get_item(self, key, lang, part):
        return self.items[key][lang][part]

    def get_langs(self, key):
        items = []
        for k, v in self.items[key]:
            items.append({"lang": k})
        return items
