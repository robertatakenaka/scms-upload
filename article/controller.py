from django.utils.translation import gettext_lazy as _
from django.db.models import Q

from article.models import Article, ArticleAuthor, ArticleTitle
from packtools.sps.models.front_journal_meta import ISSN
from packtools.sps.models.article_titles import ArticleTitles
from packtools.sps.models.article_authors import Authors

from . import exceptions


def get_or_create_official_document(xmltree):
    # TODO
    try:
        issn = ISSN(xmltree)
        article_titles = ArticleTitles(xmltree)
        article_authors = Authors(xmltree)

        return get_official_document(
            issn.epub,
            issn.ppub,
            titles=article_titles.data,
            authors=article_authors.contribs,
        )
    except Article.DoesNotExist:
        # TODO create
        return create_official_document(xmltree)

    except Article.MultipleObjectsReturned:
        return

    except:
        return


def create_official_document(xmltree):
    article = Article()

    article_titles = ArticleTitles(xmltree)
    article_authors = Authors(xmltree)

    for item in article_authors.contribs:
        reseacher = ArticleAuthor()
        reseacher.given_names = item['given_names']
        reseacher.surname = item['surname']
        article.author.add(reseacher)

    for item in article_titles.data:
        title = ArticleTitle()
        title.title = item['text']
        title.lang = item['language']
        article.title_with_lang.add(title)

    return article


def get_official_document(
        electronic_issn,
        print_issn,
        titles,
        authors):
    try:
        qs = None
        for item in titles:
            q = Q(**{
                    "title_with_lang__lang": item['languagae'],
                    "title_with_lang__title": item['text'],
                })
            qs = qs & q if qs else q
        for item in authors:
            q = Q(**{
                    "author__surname": item['surname'],
                    "author__given_names": item['given_names'],
                })
            qs = qs & q if qs else q
        official_article = Article.objects.get(
            qs,
            official_journal__ISSN_electronic=electronic_issn,
            official_journal__ISSN_print=print_issn,
        )
    except Article.DoesNotExist as e:
        raise e

    except Article.MultipleObjectsReturned as e:
        raise e

    except:
        raise exceptions.GetDocumentError(
            _('Unable to get official article {} {} {} {}').format(
                str(titles), str(authors), type(e), e
            )
        )
    return official_article
