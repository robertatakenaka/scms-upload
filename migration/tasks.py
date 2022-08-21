import logging

from django.contrib.auth import get_user_model

from config import celery_app

from . import controller


User = get_user_model()


def migrate_journals(source_file_path, connection):
    controller.connect(connection)
    for pid, data in controller.get_classic_website_records("title", source_file_path):
        task_migrate_journal.delay(pid, data)


@celery_app.task(bind=True, max_retries=3)
def task_migrate_journal(self, pid, data):
    try:
        controller.migrate_journal(pid, data)
    except (
            controller.MigratedJournalSaveError,
            controller.JournalMigrationTrackSaveError,
            ) as e:
        logging.error(e)
    try:
        controller.publish_journal(pid)
    except (
            controller.PublishJournalError,
            ) as e:
        logging.error(e)


def migrate_issues(source_file_path, connection, files_storage_config):
    controller.connect(connection)
    for pid, data in controller.get_classic_website_records("issue", source_file_path):
        task_migrate_issue.delay(pid, data, files_storage_config)


def get_files_storage(files_storage_config):

    return controller.MinioStorage(
        minio_host=files_storage_config["host"],
        minio_access_key=files_storage_config["access_key"],
        minio_secret_key=files_storage_config["secret_key"],
        bucket_root=files_storage_config["bucket_root"],
        bucket_subdir=files_storage_config["bucket_subdir"],
        minio_secure=True,
        minio_http_client=None,
    )


@celery_app.task(bind=True, max_retries=3)
def task_migrate_issue(self, pid, data, files_storage_config):
    try:
        controller.migrate_issue(pid, data)
    except (
            controller.MigratedIssueSaveError,
            controller.IssueMigrationTrackSaveError,
            ) as e:
        logging.error(e)

    try:
        files_storage_config["bucket_subdir"] = "public"
        files_storage = get_files_storage(files_storage_config)
        controller.migrate_issue_files(pid, files_storage)
    except (
            controller.IssueFilesMigrationSaveError,
            controller.IssueFilesMigrationGetError,
            ) as e:
        logging.error(e)

    try:
        controller.publish_issue(pid)
    except (
            controller.PublishIssueError,
            ) as e:
        logging.error(e)


def migrate_documents(source_file_path, connection):
    controller.connect(connection)
    for pid, data in controller.get_classic_website_records("artigo", source_file_path):
        task_migrate_document.delay(pid, data)


@celery_app.task(bind=True, max_retries=3)
def task_migrate_document(self, pid, data):
    try:
        controller.migrate_document(pid, data)
    except (
            controller.MigratedDocumentSaveError,
            controller.DocumentMigrationTrackSaveError,
            ) as e:
        logging.error(e)
    try:
        controller.publish_document(pid)
    except (
            controller.PublishDocumentError,
            ) as e:
        logging.error(e)