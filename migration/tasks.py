import logging

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from config import celery_app
from migration.models import MigratedIssue, MigratedDocument

from . import controller
from .choices import MS_IMPORTED, MS_PUBLISHED, MS_TO_IGNORE, MS_TO_MIGRATE

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
    # migra registros da base de dados title
    controller.migrate_journal_records(
        user,
        collection_acron,
        force_update,
    )


@celery_app.task(bind=True, name="migrate_issue_records")
def task_migrate_issue_records(
    self,
    username,
    collection_acron,
    force_update=False,
):
    user = _get_user(self.request, username)
    # migra registros da base de dados issue
    controller.migrate_issue_records(
        user,
        collection_acron,
        force_update,
    )


@celery_app.task(bind=True, name="migrate_document_files_and_records")
def task_migrate_document_files_and_records(
    self,
    username,
    collection_acron,
    journal_acron=None,
    publication_year=None,
    force_update=False,
):
    user = _get_user(self.request, username)

    params = {"migrated_journal__scielo_journal__collection__acron": collection_acron}
    if journal_acron:
        params["migrated_journal__scielo_journal__acron"] = journal_acron
    if publication_year:
        params["scielo_issue__official_issue__publication_year"] = publication_year

    if force_update:
        items = MigratedIssue.objects.filter(
            Q(status=MS_TO_MIGRATE) | Q(status=MS_IMPORTED),
            **params)
    else:
        items = MigratedIssue.objects.filter(Q(status=MS_TO_MIGRATE), **params)
    for migrated_issue in items.iterator():
        # migra os arquivos do issue (pdf, img, xml, html, ...)
        # migra os registros de artigo
        task_migrate_one_issue_documents.apply_async(
            kwargs={
                "username": username,
                "collection_acron": collection_acron,
                "journal_acron": migrated_issue.migrated_journal.scielo_journal.acron,
                "issue_folder": migrated_issue.scielo_issue.issue_folder,
                "force_update": force_update,
            }
        )


@celery_app.task(bind=True, name="migrate_one_issue_documents")
def task_migrate_one_issue_documents(
    self,
    username,
    collection_acron,
    journal_acron,
    issue_folder,
    force_update=False,
):
    user = _get_user(self.request, username)
    migrated_issue = MigratedIssue.get(
        collection_acron=collection_acron,
        journal_acron=journal_acron,
        issue_folder=issue_folder,
    )
    # migra os arquivos do issue (pdf, img, xml, html, ...)
    # migra os registros de artigo
    controller.migrate_one_issue_documents(
        user,
        migrated_issue,
        collection_acron,
        force_update,
    )


@celery_app.task(bind=True, name="generate_sps_packages")
def task_generate_sps_packages(
    self,
    username,
    collection_acron=None,
    journal_acron=None,
    publication_year=None,
    issue_folder=None,
    force_update=False,
):
    user = _get_user(self.request, username)
    params = {}
    if collection_acron:
        params["migrated_issue__migrated_journal__scielo_journal__collection__acron"] = (
            collection_acron
        )
    if journal_acron:
        params["migrated_issue__migrated_journal__scielo_journal__acron"] = journal_acron
    if publication_year:
        params["migrated_issue__scielo_issue__official_issue__publication_year"] = publication_year
    if issue_folder:
        params["migrated_issue__scielo_issue__issue_folder"] = issue_folder

    if force_update:
        items = MigratedDocument.objects.filter(
            Q(status=MS_TO_MIGRATE) | Q(status=MS_IMPORTED),
            **params)
    else:
        items = MigratedDocument.objects.filter(
            Q(status=MS_TO_MIGRATE), **params)
    for migrated_doc in items.iterator():
        logging.info({
            "username": username,
            "collection_acron": migrated_doc.migrated_issue.migrated_journal.scielo_journal.collection.acron,
            "pid": migrated_doc.pid,
        })
        task_generate_sps_package.apply_async(
            kwargs={
                "username": username,
                "collection_acron": migrated_doc.migrated_issue.migrated_journal.scielo_journal.collection.acron,
                "pid": migrated_doc.pid,
            }
        )


@celery_app.task(bind=True, name="generate_sps_package")
def task_generate_sps_package(
    self,
    username,
    collection_acron,
    pid,
):
    user = _get_user(self.request, username)
    try:
        migrated_document = MigratedDocument.objects.get(
            migrated_issue__migrated_journal__scielo_journal__collection__acron=collection_acron,
            pid=pid,
        )
        controller.generate_sps_package(collection_acron, user, migrated_document)
    except MigratedDocument.MultipleObjectsReturned as e:
        logging.exception(f"collection_acron: {collection_acron} pid: {pid} {e}")
        for item in MigratedDocument.objects.filter(
            migrated_issue__migrated_journal__scielo_journal__collection__acron=collection_acron,
            pid=pid,
        ).iterator():
            item.migrated_issue.status = MS_TO_MIGRATE
            item.migrated_issue.save()
            item.delete()


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
    task_migrate_issue_records.apply_async(
        kwargs={
            "username": username,
            "collection_acron": collection_acron,
            "force_update": force_update,
        }
    )
    # migra os arquivos contidos nas pastas dos fascículos
    # migra os registros das bases de artigos
    task_migrate_document_files_and_records.apply_async(
        kwargs={
            "username": username,
            "collection_acron": collection_acron,
            "force_update": force_update,
        }
    )
    # se aplicável, gera XML a partir do HTML
    # gera pacote sps
    task_generate_sps_packages.apply_async(
        kwargs={
            "username": username,
            "collection_acron": collection_acron,
        }
    )
