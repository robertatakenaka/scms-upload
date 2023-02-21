from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model

from config import celery_app

from . import controller


User = get_user_model()


@celery_app.task(bind=True, name=_('Start'))
def start(
        self,
        user_id=None,
        ):
    try:
        controller.start(self.request.user)
    except AttributeError:
        controller.start(User.objects.get(pk=user_id or 1))


@celery_app.task(bind=True, name=_('Migrate journals'))
def task_migrate_journals(
        self,
        user_id,
        collection_acron,
        force_update=False,
        ):
    user = User.objects.get(pk=user_id or 1)
    controller.migrate_journals(
        user,
        collection_acron,
        force_update,
    )


@celery_app.task(bind=True, name=_('Migrate issues'))
def task_migrate_issues(
        self,
        user_id,
        collection_acron,
        force_update=False,
        ):
    user = User.objects.get(pk=user_id or 1)
    controller.migrate_issues(
        user,
        collection_acron,
        force_update,
    )


@celery_app.task(bind=True, name=_('Migrate documents'))
def task_import_issues_files_and_migrate_documents(
        self,
        user_id,
        collection_acron,
        scielo_issn=None,
        publication_year=None,
        force_update=False,
        ):
    user = User.objects.get(pk=user_id or 1)
    controller.import_issues_files_and_migrate_documents(
        user,
        collection_acron,
        scielo_issn,
        publication_year,
        force_update,
    )
