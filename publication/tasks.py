import logging
from datetime import datetime

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from article.models import SciELOArticle
from article.tasks import task_create_or_update_articles
from collection.choices import QA
from collection.models import Collection, WebSiteConfiguration
from config import celery_app
from issue.models import SciELOIssue
from journal.models import SciELOJournal
from publication.api.publication import PublicationAPI
from publication.api.document import publish_article
from publication.api.issue import publish_issue
from publication.api.journal import publish_journal


User = get_user_model()

# try:
#     website = WebSiteConfiguration.objects.get(
#         purpose=QA,
#         enabled=True,
#         db_uri__isnull=False,
#     )
#     mk_connection(website.db_uri)
# except Exception as e:
#     pass


def _get_user(user_id, username):
    if user_id:
        return User.objects.get(pk=user_id)
    if username:
        return User.objects.get(username=username)


def _get_api_data(collection, website_kind, item_name):
    website = WebSiteConfiguration.get(
        collection=collection,
        purpose=website_kind,
    )
    url = website.api_url_article
    if item_name == "journal":
        url = website.api_url_journal
    elif item_name == "issue":
        url = website.api_url_issue

    api = PublicationAPI(
        post_data_url=url,
        get_token_url=website.api_get_token_url,
        username=website.api_username,
        password=website.api_password,
    )
    api.get_token()
    return api.data


@celery_app.task(bind=True)
def task_publish(
    self,
    user_id=None,
    username=None,
    collection_acron=None,
    force_update=False,
):
    user = _get_user(user_id, username)
    # registra articles
    task_create_or_update_articles.apply_async(
        kwargs={
            "user_id": user.id,
            "collection_acron": collection_acron,
            "force_update": force_update,
        }
    )
    # publica journals
    task_publish_journals.apply_async(
        kwargs={
            "user_id": user.id,
            "collection_acron": collection_acron,
            "force_update": force_update,
        }
    )
    # publica issues
    task_publish_issues.apply_async(
        kwargs={
            "user_id": user.id,
            "collection_acron": collection_acron,
            "force_update": force_update,
        }
    )
    # publica
    task_publish_articles.apply_async(
        kwargs={
            "user_id": user.id,
            "collection_acron": collection_acron,
            "force_update": force_update,
        }
    )


@celery_app.task(bind=True)
def task_publish_journals(
    self,
    user_id=None,
    username=None,
    website_kind=None,
    collection_acron=None,
    force_update=None,
):

    website_kind = website_kind or QA

    if collection_acron:
        collections = Collection.objects.filter(acron=collection_acron).iterator()
    else:
        collections = Collection.objects.iterator()
    if force_update:
        for collection in collections:
            for item in SciELOJournal.objects.filter(
                publication_stage__isnull=False,
                collection=collection,
            ).iterator():
                item.publication_stage = None
                item.save()

    if collection_acron:
        collections = Collection.objects.filter(acron=collection_acron).iterator()
    else:
        collections = Collection.objects.iterator()
    for collection in collections:
        api_data = _get_api_data(collection, website_kind, "journal")
        for item in SciELOJournal.items_to_publish(website_kind, collection):
            task_publish_journal.apply_async(
                kwargs=dict(
                    user_id=user_id,
                    username=username,
                    item_id=item.id,
                    api_data=api_data,
                )
            )


@celery_app.task(bind=True)
def task_publish_journal(
    self,
    user_id,
    username,
    item_id,
    api_data,
):
    user = _get_user(user_id, username)
    scielo_journal = SciELOJournal.objects.get(id=item_id)
    publish_journal(user, scielo_journal, api_data)


@celery_app.task(bind=True)
def task_publish_issues(
    self,
    user_id=None,
    username=None,
    website_kind=None,
    collection_acron=None,
    force_update=None,
):
    website_kind = website_kind or QA

    if collection_acron:
        collections = Collection.objects.filter(acron=collection_acron).iterator()
    else:
        collections = Collection.objects.iterator()
    if force_update:
        for collection in collections:
            for item in SciELOIssue.objects.filter(
                publication_stage__isnull=False,
                scielo_journal__collection=collection,
            ).iterator():
                item.publication_stage = None
                item.save()

    if collection_acron:
        collections = Collection.objects.filter(acron=collection_acron).iterator()
    else:
        collections = Collection.objects.iterator()
    for collection in collections:
        api_data = _get_api_data(collection, website_kind, "issue")
        for item in SciELOIssue.items_to_publish(
            website_kind,
            collection=collection,
        ):
            task_publish_issue.apply_async(
                kwargs=dict(
                    user_id=user_id,
                    username=username,
                    item_id=item.id,
                    api_data=api_data,
                )
            )


@celery_app.task(bind=True)
def task_publish_issue(
    self,
    user_id,
    username,
    item_id,
    api_data,
):
    user = _get_user(user_id, username)
    scielo_issue = SciELOIssue.objects.get(id=item_id)
    publish_issue(user, scielo_issue, api_data)


@celery_app.task(bind=True)
def task_publish_articles(
    self,
    user_id=None,
    username=None,
    website_kind=None,
    collection_acron=None,
    force_update=None,
):
    website_kind = website_kind or QA

    if collection_acron:
        collections = Collection.objects.filter(acron=collection_acron).iterator()
    else:
        collections = Collection.objects.iterator()
    if force_update:
        for collection in collections:
            logging.info(collection)
            SciELOArticle.objects.filter(
                publication_stage__isnull=False,
                collection=collection,
            ).update(publication_stage=None)

    if collection_acron:
        collections = Collection.objects.filter(acron=collection_acron).iterator()
    else:
        collections = Collection.objects.iterator()
    for collection in collections:
        api_data = _get_api_data(collection, website_kind, "article")

        items = SciELOArticle.items_to_publish(website_kind)
        for item in items:
            task_publish_article.apply_async(
                kwargs=dict(
                    user_id=user_id,
                    username=username,
                    item_id=item.id,
                    api_data=api_data,
                )
            )


@celery_app.task(bind=True)
def task_publish_article(
    self,
    user_id,
    username,
    item_id,
    api_data,
):
    user = _get_user(user_id, username)
    scielo_article = SciELOArticle.objects.get(id=item_id)
    publish_article(user, scielo_article, api_data)
