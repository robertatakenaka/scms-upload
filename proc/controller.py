import logging
import sys

from django.conf import settings
from requests.exceptions import HTTPError 

from collection.models import Collection
from collection.choices import PUBLIC, QA
from core.utils.requester import fetch_data
from issue.models import Issue
from journal.models import (
    Journal,
    OfficialJournal,
    Subject,
    Institution,
    Publisher,
    Institution,
    Owner,
    JournalCollection,
    JournalHistory,
)
from migration import controller
from pid_provider.models import PidProviderConfig
from proc.models import IssueProc, JournalProc, ArticleProc
from publication.api.issue import publish_issue
from publication.api.journal import publish_journal
from publication.api.publication import get_api_data, PublicationAPI
from tracker import choices as tracker_choices
from tracker.models import UnexpectedEvent


class FetchMultipleJournalsError(Exception):
    pass


class UnableToGetJournalDataFromCoreError(Exception):
    pass


class UnableToCreateIssueProcsError(Exception):
    pass


try:
    core_timeout = PidProviderConfig.objects.filter(timeout__isnull=False).first().timeout
except Exception as e:
    core_timeout = 5


def create_or_update_journal(
    journal_title, issn_electronic, issn_print, user, force_update=None
):
    # esta função por enquanto é chamada somente no fluxo de ingresso de conteúdo novo
    # no fluxo de migração, existe migration.controller.create_or_update_journal
    if not force_update:
        try:
            return Journal.get_registered(journal_title, issn_electronic, issn_print)
        except Journal.DoesNotExist:
            pass

    try:
        fetch_and_create_journal(
            journal_title, issn_electronic, issn_print, user, force_update
        )
    except FetchMultipleJournalsError as exc:
        raise exc
    except Exception as exc:
        pass

    try:
        return Journal.get_registered(journal_title, issn_electronic, issn_print)
    except Journal.DoesNotExist as exc:
        return None


def fetch_and_create_journal(
    journal_title,
    issn_electronic,
    issn_print,
    user,
    force_update=None,
):
    try:
        params = {
            "issn_print": issn_print,
            "issn_electronic": issn_electronic,
        }
        params = {k: v for k, v in params.items() if v}
        response = fetch_data(
            url=settings.JOURNAL_API_URL,
            params=params,
            json=True,
            timeout=core_timeout or 5,
        )
        logging.info(response)
    except Exception as e:
        logging.exception(e)
        return

    if response["count"] > 1:
        raise FetchMultipleJournalsError(f"{settings.JOURNAL_API_URL} with {params} returned {response['count']} journals. Ask for support to solve this issue")

    for result in response.get("results") or []:
        official = result["official"]
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
            title=result.get("title"),
            short_title=result.get("short_title"),
        )
        journal.license_code = (result.get("journal_use_license") or {}).get("license_type")
        journal.nlm_title = result.get("nlm_title")
        journal.doi_prefix = result.get("doi_prefix")
        journal.save()

        for item in result.get("Subject") or []:
            journal.subjects.add(Subject.create_or_update(user, item["value"]))

        for item in result.get("publisher") or []:
            institution = Institution.get_or_create(
                inst_name=item["name"],
                acronym=None,
                level_1=None,
                level_2=None,
                level_3=None,
                location=None,
                user=user,
            )
            journal.publisher.add(Publisher.create_or_update(user, journal, institution))

        for item in result.get("owner") or []:
            institution = Institution.get_or_create(
                inst_name=item["name"],
                acronym=None,
                level_1=None,
                level_2=None,
                level_3=None,
                location=None,
                user=user,
            )
            journal.owner.add(Owner.create_or_update(user, journal, institution))

        for item in result.get("scielo_journal") or []:
            try:
                collection = Collection.objects.get(acron=item["collection_acron"])
            except Collection.DoesNotExist:
                continue

            journal_proc = JournalProc.get_or_create(user, collection, item["issn_scielo"])
            journal_proc.update(
                user=user,
                journal=journal,
                acron=item["journal_acron"],
                title=journal.title,
                availability_status="C",
                migration_status=tracker_choices.PROGRESS_STATUS_DONE,
                force_update=force_update,
            )
            journal.journal_acron = item.get("journal_acron")
            journal_collection = JournalCollection.create_or_update(
                user, collection, journal
            )
            for jh in item.get("journal_history") or []:
                JournalHistory.create_or_update(
                    user,
                    journal_collection,
                    jh["event_type"],
                    jh["year"],
                    jh["month"],
                    jh["day"],
                    jh["interruption_reason"],
                )


def create_or_update_issue(journal, pub_year, volume, suppl, number, user, force_update=None):
    # esta função por enquanto é chamada somente no fluxo de ingresso de conteúdo novo
    # no fluxo de migração, existe migration.controller.create_or_update_issue
    if not force_update:
        try:
            return Issue.get(
                journal=journal,
                volume=volume,
                supplement=suppl,
                number=number,
            )
        except Issue.DoesNotExist:
            pass

    try:
        fetch_and_create_issues(
            journal, pub_year, volume, suppl, number, user)
    except Exception as exc:
        pass

    try:
        return Issue.get(
            journal=journal,
            volume=volume,
            supplement=suppl,
            number=number,
        )
    except Issue.DoesNotExist as exc:
        return None


@staticmethod
def fetch_and_create_issues(journal, pub_year, volume, suppl, number, user):
    if journal:
        issn_print = journal.official_journal.issn_print
        issn_electronic = journal.official_journal.issn_electronic
        try:
            params = {
                "issn_print": issn_print,
                "issn_electronic": issn_electronic,
                "volume": volume,
            }
            params = {k: v for k, v in params.items() if v}
            logging.info(params)
            response = fetch_data(
                url=settings.ISSUE_API_URL,
                params=params,
                json=True,
                timeout=5,
            )

        except Exception as e:
            logging.exception(e)
            return

        logging.info(f"REsponse {response}")
        issue = None
        for result in response.get("results"):
            logging.info(f"result: {result}")
            issue = Issue.get_or_create(
                journal=journal,
                volume=result["volume"],
                supplement=result["supplement"],
                number=result["number"],
                publication_year=result["year"],
                user=user,
            )

            for journal_proc in JournalProc.objects.filter(journal=journal):
                try:
                    issue_proc = IssueProc.objects.get(
                        collection=journal_proc.collection, issue=issue
                    )
                except IssueProc.DoesNotExist:
                    issue_pid_suffix = str(issue.order).zfill(4)
                    issue_proc = IssueProc.get_or_create(
                        user,
                        journal_proc.collection,
                        pid=f"{journal_proc.pid}{issue.publication_year}{issue_pid_suffix}",
                    )
                    issue_proc.journal_proc = journal_proc
                    issue_proc.save()


def create_or_update_migrated_journal(
    user,
    collection,
    classic_website,
    force_update,
):
    for (
        scielo_issn,
        journal_data,
    ) in classic_website.get_journals_pids_and_records():
        # para cada registro da base de dados "title",
        # cria um registro MigratedData (source="journal")
        try:
            JournalProc.register_classic_website_data(
                user,
                collection,
                scielo_issn,
                journal_data[0],
                "journal",
                force_update,
            )

        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            UnexpectedEvent.create(
                e=e,
                exc_traceback=exc_traceback,
                detail={
                    "task": "proc.controller.create_or_update_migrated_journal",
                    "user_id": user.id,
                    "username": user.username,
                    "collection": collection.acron,
                    "pid": scielo_issn,
                    "force_update": force_update,
                },
            )


def create_or_update_migrated_issue(
    user,
    collection,
    classic_website,
    force_update,
):
    for (
        pid,
        issue_data,
    ) in classic_website.get_issues_pids_and_records():
        # para cada registro da base de dados "issue",
        # cria um registro MigratedData (source="issue")
        try:
            IssueProc.register_classic_website_data(
                user,
                collection,
                pid,
                issue_data[0],
                "issue",
                force_update,
            )

        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            UnexpectedEvent.create(
                e=e,
                exc_traceback=exc_traceback,
                detail={
                    "task": "proc.controller.create_or_update_migrated_issue",
                    "user_id": user.id,
                    "username": user.username,
                    "collection": collection.acron,
                    "pid": pid,
                    "force_update": force_update,
                },
            )


def migrate_journal(
    user, journal_proc, issue_filter, force_update, force_import, migrate_issues, migrate_articles
):
    try:
        # cria ou atualiza Journal e atualiza journal_proc
        journal_proc.create_or_update_item(
            user, force_update, controller.create_or_update_journal
        )
        # acron.id
        controller.register_acron_id_file_content(
            user,
            journal_proc,
            force_update=force_import,
        )

        if migrate_issues:
            items = IssueProc.items_to_process(journal_proc.collection, "issue", issue_filter, force_update)
            logging.info(f"issues to process: {items.count()}")
            logging.info(f"issue_filter: {issue_filter}")
            logging.info(list(IssueProc.items_to_process_info(items)))

            for issue_proc in items:
                migrate_issue(user, issue_proc, force_update, force_import, migrate_articles)

    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        UnexpectedEvent.create(
            e=e,
            exc_traceback=exc_traceback,
            detail={
                "task": "proc.controller.migrate_journal",
                "user_id": user.id,
                "username": user.username,
                "collection": collection.acron,
                "pid": journal_proc.pid,
                "issue_filter": issue_filter,
                "force_update": force_update,
                "force_import": force_import,
                "migrate_issues": migrate_issues,
                "migrate_articles": migrate_articles,
            },
        )


def migrate_issue(user, issue_proc, force_update, force_import, migrate_articles):
    try:
        issue_proc.create_or_update_item(
            user,
            force_update,
            controller.create_or_update_issue,
            JournalProc=JournalProc,
        )

        issue_proc.migrate_document_records(
            user,
            force_update=force_import,
        )

        issue_proc.get_files_from_classic_website(
            user, force_update, controller.import_one_issue_files
        )

        article_filter = {"issue_proc": issue_proc}
        if migrate_articles:
            items = ArticleProc.items_to_process(issue_proc.collection, "article", article_filter, force_update)
            logging.info(f"articles to process: {items.count()}")
            logging.info(f"article_filter: {article_filter}")
            logging.info(list(ArticleProc.items_to_process_info(items)))
            for article_proc in items:
                article_proc.migrate_article(user, force_update)
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        UnexpectedEvent.create(
            e=e,
            exc_traceback=exc_traceback,
            detail={
                "task": "proc.controller.migrate_issue",
                "user_id": user.id,
                "username": user.username,
                "collection": collection.acron,
                "pid": issue_proc.pid,
                "force_update": force_update,
                "force_import": force_import,
                "migrate_articles": migrate_articles,
            },
        )


def publish_journals(
    user,
    website_kind,
    collection,
    journal_filter,
    issue_filter,
    force_update,
    run_publish_issues,
    run_publish_articles,
    task_publish_article,
):
    params = dict(
        website_kind=website_kind,
        collection=collection,
        journal_filter=journal_filter,
        issue_filter=issue_filter,
        force_update=force_update,
        run_publish_issues=run_publish_issues,
        run_publish_articles=run_publish_articles,
        task_publish_article="call task_publish_article" if task_publish_article else None
    )
    logging.info(f"publish_journals {params}")
    api_data = get_api_data(collection, "journal", website_kind)

    if api_data.get("error"):
        logging.error(api_data)
    else:
        items = JournalProc.items_to_publish(
            website_kind=website_kind,
            content_type="journal",
            collection=collection,
            force_update=force_update,
            params=journal_filter,
        )
        logging.info(f"publish_journals: {items.count()}")
        for journal_proc in items:
            published = journal_proc.publish(
                user,
                publish_journal,
                website_kind=website_kind,
                api_data=api_data,
                force_update=force_update,
            )
            if run_publish_issues and published:
                publish_issues(
                    user,
                    website_kind,
                    journal_proc,
                    issue_filter,
                    force_update,
                    run_publish_articles,
                    task_publish_article,
                )


def publish_issues(
    user,
    website_kind,
    journal_proc,
    issue_filter,
    force_update,
    run_publish_articles,
    task_publish_article,
):
    collection = journal_proc.collection
    params = dict(
        website_kind=website_kind,
        collection=collection,
        journal_proc=journal_proc,
        issue_filter=issue_filter,
        force_update=force_update,
        run_publish_articles=run_publish_articles,
        task_publish_article="call task_publish_article" if task_publish_article else None
    )
    logging.info(f"publish_issues {params}")
    api_data = get_api_data(collection, "issue", website_kind)

    if api_data.get("error"):
        logging.error(api_data)
    else:
        items = IssueProc.items_to_publish(
            website_kind=website_kind,
            content_type="issue",
            collection=collection,
            force_update=force_update,
            params=issue_filter,
        )
        logging.info(f"publish_issues: {items.count()}")
        for issue_proc in items:
            published = issue_proc.publish(
                user,
                publish_issue,
                website_kind=website_kind,
                api_data=api_data,
                force_update=force_update,
            )
            if run_publish_articles and published:
                publish_articles(
                    user,
                    website_kind,
                    issue_proc,
                    force_update,
                    task_publish_article,
                )


def publish_articles(
    user, website_kind, issue_proc, force_update, task_publish_article
):
    collection = issue_proc.collection
    params = dict(
        website_kind=website_kind,
        collection=collection,
        issue_proc=issue_proc,
        force_update=force_update,
        task_publish_article="call task_publish_article" if task_publish_article else None
    )
    logging.info(f"publish_articles {params}")
    api_data = get_api_data(collection, "article", website_kind)
    if api_data.get("error"):
        logging.error(api_data)
    else:
        items = ArticleProc.items_to_publish(
            website_kind=website_kind,
            content_type="article",
            collection=collection,
            force_update=force_update,
            params={"issue_proc": issue_proc},
        )
        logging.info(f"publish_articles: {items.count()}")
        for article_proc in items:
            task_publish_article.apply_async(
                kwargs=dict(
                    user_id=user.id,
                    username=user.username,
                    website_kind=website_kind,
                    article_proc_id=article_proc.id,
                    api_data=api_data,
                    force_update=force_update,
                )
            )
