from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from config import celery_app
from migration.models import MigratedIssue

from . import controller
from .choices import MS_IMPORTED, MS_PUBLISHED, MS_TO_IGNORE

User = get_user_model()


def _get_user(request, username):
    try:
        return User.objects.get(pk=request.user.id)
    except AttributeError:
        return User.objects.get(username=username)


@celery_app.task(bind=True, name=_("schedule_migrations"))
def task_schedule_migrations(
    self,
    username=None,
    collection_acron=None,
):
    user = _get_user(self.request, username)
    controller.schedule_migrations(user, collection_acron)


@celery_app.task(bind=True, name="migrate_journal_records")
def task_migrate_journal_records(
    self,
    username,
    collection_acron,
    force_update=False,
):
    user = _get_user(self.request, username)
    controller.migrate_journal_records(
        user,
        collection_acron,
        force_update,
    )


@celery_app.task(bind=True, name="migrate_issue_records_and_files")
def task_migrate_issue_records_and_files(
    self,
    username,
    collection_acron,
    force_update=False,
):
    user = _get_user(self.request, username)
    controller.migrate_issue_records_and_files(
        user,
        collection_acron,
        force_update,
    )


@celery_app.task(bind=True, name="migrate_set_of_issue_files")
def task_migrate_set_of_issue_files(
    self,
    username,
    collection_acron,
    scielo_issn=None,
    publication_year=None,
    force_update=False,
):
    user = _get_user(self.request, username)

    params = {"migrated_journal__scielo_journal__collection__acron": collection_acron}
    if scielo_issn:
        params["migrated_journal__scielo_journal__scielo_issn"] = scielo_issn
    if publication_year:
        params["scielo_issue__official_issue__publication_year"] = publication_year

    items = MigratedIssue.objects.filter(
        Q(status=MS_PUBLISHED) | Q(status=MS_IMPORTED),
        **params,
    )
    for migrated_issue in items.iterator():
        task_migrate_one_issue_files.apply_async(
            kwargs={
                "username": username,
                "migrated_issue_id": migrated_issue.id,
                "collection_acron": collection_acron,
                "force_update": force_update,
            }
        )


@celery_app.task(bind=True, name="migrate_one_issue_files")
def task_migrate_one_issue_files(
    self,
    username,
    migrated_issue_id,
    collection_acron,
    force_update=False,
):
    user = _get_user(self.request, username)
    migrated_issue = MigratedIssue.objects.get(id=migrated_issue_id)
    controller.migrate_one_issue_files(
        user,
        migrated_issue,
        collection_acron,
        force_update,
    )


@celery_app.task(bind=True, name="migrate_set_of_issue_document_records")
def task_migrate_set_of_issue_document_records(
    self,
    username,
    collection_acron,
    scielo_issn=None,
    publication_year=None,
    force_update=False,
):
    user = _get_user(self.request, username)

    params = {"migrated_journal__scielo_journal__collection__acron": collection_acron}
    if scielo_issn:
        params["migrated_journal__scielo_journal__scielo_issn"] = scielo_issn
    if publication_year:
        params["scielo_issue__official_issue__publication_year"] = publication_year

    items = MigratedIssue.objects.filter(
        Q(status=MS_PUBLISHED) | Q(status=MS_IMPORTED),
        **params,
    )
    for migrated_issue in items.iterator():
        task_migrate_one_issue_document_records.apply_async(
            kwargs={
                "username": username,
                "migrated_issue_id": migrated_issue.id,
                "collection_acron": collection_acron,
                "force_update": force_update,
            }
        )


@celery_app.task(bind=True, name="migrate_one_issue_document_records")
def task_migrate_one_issue_document_records(
    self,
    username,
    migrated_issue_id,
    collection_acron,
    force_update=False,
):
    user = _get_user(self.request, username)
    migrated_issue = MigratedIssue.objects.get(id=migrated_issue_id)
    controller.migrate_one_issue_document_records(
        user,
        migrated_issue,
        collection_acron,
        force_update,
    )


@celery_app.task(bind=True, name="generate_sps_packages")
def task_generate_sps_packages(
    self,
    username,
    collection_acron,
    kwargs=None,
):
    user = _get_user(self.request, username)
    controller.generate_sps_packages(
        user,
        collection_acron,
        kwargs,
    )


@celery_app.task(bind=True, name=_("run_migrations"))
def task_run_migrations(
    self,
    username=None,
    collection_acron=None,
    force_update=False,
):
    user = _get_user(self.request, username)
    # migra os registros da base TITLE
    task_migrate_journal_records.apply_async(
        kwargs={
            "username": username,
            "collection_acron": collection_acron,
            "force_update": force_update,
        }
    )
    # migra os registros da base ISSUE
    # migra os arquivos contidos nas pastas dos fascículos
    task_migrate_issue_records_and_files.apply_async(
        kwargs={
            "username": username,
            "collection_acron": collection_acron,
            "force_update": force_update,
        }
    )
    # migra os registros das bases de artigos
    # se aplicável, gera XML a partir do HTML
    # gera SPS package
    task_migrate_set_of_issue_document_records.apply_async(
        kwargs={
            "username": username,
            "collection_acron": collection_acron,
            "force_update": force_update,
        }
    )
    # gera pacote sps dos dados e arquivos de migrated document
    task_generate_sps_packages.apply_async(
        kwargs={
            "username": username,
            "collection_acron": collection_acron,
            "kwargs": {},
        }
    )
