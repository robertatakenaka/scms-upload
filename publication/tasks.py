import logging

from django.db.models import Q
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from . import controller
from article.models import ArticlePackages, Article
from article import controller
from article.choices import AS_READ_TO_PUBLISH
from journal.models import SciELOJournal
from journal.choices import CURRENT
from publication.models import WebSiteConfiguration
from publication.choices import QA
from config import celery_app


User = get_user_model()


def _get_user(request, username):
    try:
        return User.objects.get(pk=request.user.id)
    except AttributeError:
        return User.objects.get(username=username)


@celery_app.task(bind=True, name="publish_articles")
def task_publish_articles(
    self,
    username,
    website_kind,
):

    items = ArticlePackages.objects.filter(
        article__status=AS_READ_TO_PUBLISH,
    )
    for article_pkgs in items.iterator():
        task_publish_article.apply_async(
            kwargs={
                "username": username,
                "article_pkgs_id": article_pkgs.id,
                "website_kind": website_kind,
            }
        )


@celery_app.task(bind=True, name="publish_article")
def task_publish_article(
    self,
    username,
    article_pkgs_id,
    website_kind,
):
    user = _get_user(self.request, username)
    article_pkgs = ArticlePackages.objects.get(id=article_pkgs_id)

    journal = article_pkgs.article.journal or article_pkgs.article.issue.journal

    if not journal.official_journal:
        logging.warning(f"No journal found for {article_pkgs}")
        return

    for scielo_journal in SciELOJournal.objects.filter(
        official=journal.official_journal,
        availability_status=CURRENT,
    ).iterator():
        if not scielo_journal.collection:
            logging.warning(f"No collection found for {scielo_journal}")
            continue
        website = WebSiteConfiguration.get(
            collection=scielo_journal.collection,
            purpose=website_kind,
        )
        mk_connection(host, alias=None)
