import logging

from django.utils.translation import gettext_lazy as _

from config import celery_app
from celery.exceptions import SoftTimeLimitExceeded

from . import controller


@celery_app.task(bind=True, name=_('Schedule migration starter tasks'))
def task_create_tasks(
        self,
        user_id,
        collection_acron,
        ):
    controller.create_migration_starter_tasks(collection_acron, user_id)


@celery_app.task(bind=True, name=_('Schedule issues migrations tasks'))
def task_create_tasks(
        self,
        user_id,
        collection_acron,
        ):
    controller.create_tasks_to_migrate_issues_components(
        collection_acron,
        user_id,
    )


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


@celery_app.task(bind=True, name=_('Migrate and publish issues'))
def task_migrate_and_publish_issues(
        self,
        user_id,
        collection_acron,
        source_file_path=None,
        force_update=False,
        db_uri=None,
        ):
    controller.migrate_and_publish_issues(
        user_id,
        collection_acron,
        source_file_path,
        force_update,
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


@celery_app.task(bind=True, name=_('Migrate and publish documents'))
def task_migrate_issue_files_and_documents__and__publish_documents(
        self,
        user_id,
        collection_acron,
        scielo_issn=None,
        publication_year=None,
        files_storage_config=None,
        classic_ws_config=None,
        db_uri=None,
        source_file_path=None,
        force_update=False,
        ):
    controller.migrate_issue_files_and_documents__and__publish_documents(
        user_id,
        collection_acron,
        scielo_issn,
        publication_year,
        files_storage_config,
        classic_ws_config,
        db_uri,
        source_file_path,
        force_update,
        )


# @celery_app.task(bind=True, name=_('Migrate documents'))
# def task_migrate_documents(
#         user_id,
#         collection_acron,
#         source_file_path=None,
#         scielo_issn=None,
#         publication_year=None,
#         files_storage_config=None,
#         force_update=False,
#         ):
#     controller.migrate_documents(
#         user_id,
#         collection_acron,
#         source_file_path,
#         scielo_issn,
#         publication_year,
#         files_storage_config,
#         force_update,
#         )


# @celery_app.task(bind=True, name=_('Publish documents'))
# def task_publish_documents(
#         user_id,
#         collection_acron,
#         scielo_issn=None,
#         publication_year=None,
#         files_storage_config=None,
#         db_uri=None,
#         force_update=False,
#         ):
#     controller.publish_documents(
#         user_id,
#         collection_acron,
#         scielo_issn,
#         publication_year,
#         files_storage_config,
#         db_uri,
#         force_update,
#         )
