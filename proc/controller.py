import logging
import sys

from django.conf import settings

from collection.models import Collection
from core.utils.requester import fetch_data
from migration import controller
from proc.models import IssueProc, JournalProc
from journal.models import Journal, OfficialJournal
from publication.api.issue import publish_issue
from publication.api.journal import publish_journal
from publication.api.publication import get_api_data
from tracker.models import UnexpectedEvent


class UnableToGetJournalDataFromCoreError(Exception):
    pass


class UnableToCreateIssueProcsError(Exception):
    pass


def migrate_and_publish_journals(
    user, collection, classic_website, force_update, import_acron_id_file=False
):
    api_data = get_api_data(collection, "journal", website_kind="QA")
    for (
        scielo_issn,
        journal_data,
    ) in classic_website.get_journals_pids_and_records():
        # para cada registro da base de dados "title",
        # cria um registro MigratedData (source="journal")
        try:
            journal_proc = JournalProc.register_classic_website_data(
                user,
                collection,
                scielo_issn,
                journal_data[0],
                "journal",
                force_update,
            )
            # cria ou atualiza Journal e atualiza journal_proc
            journal_proc.create_or_update_item(
                user, force_update, controller.create_or_update_journal
            )
            # acron.id
            if import_acron_id_file:
                controller.register_acron_id_file_content(
                    user,
                    journal_proc,
                    force_update,
                )
            journal_proc.publish(
                user,
                publish_journal,
                api_data=api_data,
                force_update=force_update,
            )

        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            UnexpectedEvent.create(
                e=e,
                exc_traceback=exc_traceback,
                detail={
                    "task": "proc.controller.migrate_and_publish_journals",
                    "user_id": user.id,
                    "username": user.username,
                    "collection": collection.acron,
                    "pid": scielo_issn,
                    "force_update": force_update,
                },
            )


def migrate_and_publish_issues(
    user,
    collection,
    classic_website,
    force_update,
    get_files_from_classic_website=False,
):
    api_data = get_api_data(collection, "issue", website_kind="QA")
    for (
        pid,
        issue_data,
    ) in classic_website.get_issues_pids_and_records():
        # para cada registro da base de dados "issue",
        # cria um registro MigratedData (source="issue")
        try:
            issue_proc = IssueProc.register_classic_website_data(
                user,
                collection,
                pid,
                issue_data[0],
                "issue",
                force_update,
            )
            issue_proc.create_or_update_item(
                user,
                force_update,
                controller.create_or_update_issue,
                JournalProc=JournalProc,
            )
            issue_proc.publish(
                user,
                publish_issue,
                api_data=api_data,
                force_update=force_update,
            )

            if get_files_from_classic_website:
                issue_proc.get_files_from_classic_website(
                    user, force_update, controller.import_one_issue_files
                )
        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            UnexpectedEvent.create(
                e=e,
                exc_traceback=exc_traceback,
                detail={
                    "task": "proc.controller.migrate_and_publish_issues",
                    "user_id": user.id,
                    "username": user.username,
                    "collection": collection.acron,
                    "pid": pid,
                    "force_update": force_update,
                },
            )


def fetch_and_create_journal(
    journal_title,
    issn_electronic,
    issn_print,
    user,
):
    response = fetch_journal_data(journal_title, issn_electronic, issn_print)
    if response:
        for journal_data in response.get("results"):
            return create_journal_from_fetched_data(journal_data, user)


def fetch_journal_data(
    journal_title,
    issn_electronic,
    issn_print,
):
    try:
        return fetch_data(
            url=settings.JOURNAL_API_URL,
            params={
                "title": journal_title,
                "issn_print": issn_print,
                "issn_electronic": issn_electronic,
            },
            json=True,
        )
    except Exception as e:
        logging.exception(e)
        return


def create_journal_from_fetched_data(
    journal_data,
    user,
):
    official = journal_data["official"]
    official_journal = OfficialJournal.create_or_update(
        title=official["title"],
        title_iso=official["iso_short_title"],
        issn_print=official["issn_print"],
        issn_electronic=official["issn_electronic"],
        issnl=official["issnl"],
        foundation_year=official.get("foundation_year"),
        user=user,
    )
    journal = Journal.create_or_update(
        user=user,
        official_journal=official_journal,
        title=journal_data.get("title"),
        short_title=journal_data.get("short_title"),
    )
    # TODO journal collection events, dados das coleções (acron, pid, ...)
    return journal


def create_journal_procs(user, journal):
    if not JournalProc.objects.filter(journal=journal).exists():
        journal_title = journal.title or journal.official_journal.title
        issn_electronic = journal.official_journal.issn_electronic
        issn_print = journal.official_journal.issn_print

        response = fetch_journal_data(journal_title, issn_electronic, issn_print)
        if response:
            for journal_data in response.get("results"):
                for item in journal_data["scielo_journal"]:
                    _collection = Collection.objects.get(collection__acron=item["collection"])
                    journal_proc = JournalProc.get_or_create(
                        user, _collection, item["issn_scielo"],
                    )
                    journal_proc.acron = item["journal_acron"]
                    journal_proc.save()
                    yield journal_proc
        else:
            raise UnableToGetJournalDataFromCoreError(
                f"Unable to get journal data {journal} from Core"
            )


def fetch_and_create_issue(journal, volume, suppl, number, user):
    response = fetch_issue_data(journal, volume, suppl, number)
    if response:
        for issue_data in response.get("results"):
            return create_issue_from_fetched_data(issue_data, user)


def fetch_issue_data(journal, volume, suppl, number, user):
    if journal and any((volume, number)):
        issn_print = journal.official_journal.issn_print
        issn_electronic = journal.official_journal.issn_electronic
        try:
            return fetch_data(
                url=settings.ISSUE_API_URL,
                params={
                    "issn_print": issn_print,
                    "issn_electronic": issn_electronic,
                    "number": number,
                    "supplement": suppl,
                    "volume": volume,
                },
                json=True,
            )

        except Exception as e:
            logging.exception(e)
            return


def create_issue_from_fetched_data(journal, volume, suppl, number, user):
    for issue in response.get("results"):
        issue = Issue.get_or_create(
            journal=journal,
            volume=issue["volume"],
            supplement=issue["supplement"],
            number=issue["number"],
            publication_year=issue["year"],
            user=user,
        )
        return issue


def create_issue_procs(user, issue):
    if not IssueProc.objects.filter(issue=issue).exists():
        response = fetch_issue_data(issue.journal, issue.volume, issue.suppl, issue.number)
        try:
            for issue_data in response.get("results"):
                try:
                    for item in issue_data["scielo_issue"]:
                        _collection = Collection.objects.get(collection__acron=item["collection"])
                        journal_proc = JournalProc.objects.get(collection=_collection, journal=issue.journal)
                        issue_proc = IssueProc.get_or_create(
                            user, _collection, item["pid"],
                        )
                        issue_proc.journal_proc = journal_proc
                        issue_proc.save()
                        yield issue_proc
                except Exception as e:
                    raise UnableToCreateIssueProcsError()
        except Exception as e:
            raise UnableToCreateIssueProcsError(
                f"Unable to get issue data {issue} from Core"
            )
