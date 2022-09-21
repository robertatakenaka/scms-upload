import os
import logging

from django.utils.translation import gettext_lazy as _

from config import celery_app
from celery.exceptions import SoftTimeLimitExceeded

from . import controller


@celery_app.task(bind=True, name=_('Migrate and publish journals'))
def task_migrate_and_publish_journals(
        self,
        user_id,
        collection_acron,
        source_file_path=None,
        force_update=False,
        db_uri=None,
        ):
    controller.migrate_and_publish_journals(
        user_id,
        collection_acron,
        source_file_path,
        force_update,
        db_uri,
    )


@celery_app.task(bind=True, name=_('Migrate journals'))
def task_migrate_journals(
        self,
        user_id,
        collection_acron,
        source_file_path=None,
        force_update=False,
        ):
    controller.migrate_journals(
        user_id,
        collection_acron,
        source_file_path,
        force_update,
    )


@celery_app.task(bind=True, name=_('Publish migrated journals'))
def task_publish_migrated_journals(
        self,
        user_id,
        collection_acron,
        db_uri=None,
        ):
    controller.publish_migrated_journals(
        user_id,
        collection_acron,
        db_uri,
    )


@celery_app.task(bind=True, name=_('Migrate issues'))
def task_migrate_issues(
        self,
        user_id,
        collection_acron,
        source_file_path=None,
        force_update=False,
        ):
    try:
        controller.migrate_issues(
            user_id,
            collection_acron,
            source_file_path,
            force_update,
        )
    except SoftTimeLimitExceeded as e:
        logging.exception("Error as running migrate issues %s" % e)


@celery_app.task(bind=True, name=_('Publish migrated issues'))
def task_publish_migrated_issues(
        self,
        user_id,
        collection_acron,
        db_uri=None,
        ):
    controller.publish_migrated_issues(
        user_id,
        collection_acron,
        db_uri,
    )


@celery_app.task(bind=True, name=_('Migrate issues files'))
def task_migrate_issues_files(
        self,
        user_id,
        collection_acron,
        scielo_issn=None,
        files_storage_config=None,
        classic_ws_config=None,
        ):
    controller.migrate_issues_files(
        user_id,
        collection_acron,
        scielo_issn=None,
        files_storage_config=None,
        classic_ws_config=None,
    )


