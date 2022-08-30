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
    controller.migrate_and_publish_journal(pid, data)


def migrate_issues(source_file_path, connection, files_storage_config):
    controller.connect(connection)
    for pid, data in controller.get_classic_website_records("issue", source_file_path):
        task_migrate_issue.delay(pid, data)
        task_migrate_issue_files.delay(pid, data, files_storage_config)


@celery_app.task(bind=True, max_retries=3)
def task_migrate_issue(self, pid, data):
    controller.migrate_and_publish_issue(pid, data)


@celery_app.task(bind=True, max_retries=3)
def task_migrate_issue_files(self, pid, data, files_storage_config):
    controller.migrate_issue_files(pid, data, files_storage_config)


def migrate_documents(source_file_path, connection, files_storage_config):
    controller.connect(connection)
    for pid, data in controller.get_classic_website_records("artigo", source_file_path):
        task_migrate_document.delay(pid, data, files_storage_config)


@celery_app.task(bind=True, max_retries=3)
def task_migrate_document(self, pid, data, files_storage_config):
    controller.migrate_and_publish_document(pid, data, files_storage_config)
