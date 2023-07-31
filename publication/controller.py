import logging

from django.db.models import Q
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _
from packtools.sps.models.article_and_subarticles import ArticleAndSubArticles
from packtools.sps.models.article_authors import Authors
from packtools.sps.models.article_doi_with_lang import DoiWithLang
from packtools.sps.models.article_ids import ArticleIds
from packtools.sps.models.article_license import ArticleLicense
from packtools.sps.models.article_titles import ArticleTitles
from packtools.sps.models.article_toc_sections import ArticleTocSections
from packtools.sps.models.dates import ArticleDates
from packtools.sps.models.front_articlemeta_issue import ArticleMetaIssue
from packtools.sps.models.funding_group import FundingGroup
from packtools.sps.models.journal_meta import Title as Journal
from packtools.sps.models.kwd_group import KwdGroup

from . import controller
from article.models import ArticlePackages, Article
from article import controller
from article.choices import AS_READ_TO_PUBLISH
from journal.models import SciELOJournal
from journal.choices import CURRENT
from publication.models import WebSiteConfiguration
from publication.choices import QA
from publication.website.document import Document
from config import celery_app


def journal_websites(journal):
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
        yield WebSiteConfiguration.get(
            collection=scielo_journal.collection,
            purpose=website_kind,
        )


def register_document(
    xmltree, journal, issue, xml, pdfs, htmls, suppl_mats, other_pids
):
    doc = _create(xmltree, other_pids)

    doc.add_journal(journal)
    doc.add_issue(issue)
    doc.add_xml(xml)
    _add_html(doc, htmls)
    _add_pdf(doc, pdfs)
    _add_mat_suppl(doc, suppl_mats)

    _add_main_metadata(doc, xmltree)
    _add_in_issue(doc, xmltree)
    _add_publication_date(doc, xmltree)
    _add_author(doc, xmltree)
    _add_translated_title(doc, xmltree)
    _add_section(doc, xmltree)
    _add_abstract(doc, xmltree)
    _add_keywords(doc, xmltree)
    _add_doi_with_lang(doc, xmltree)
    _add_related_article(doc, xmltree)
    doc.publish_document()


def _create(xmltree, other_pids):
    xml = ArticleIds(xmltree)

    doc = Document(xml.v3)

    doc.add_identifiers(xml.v2, xml.aop_pid)
    for other_pid in other_pids or []:
        doc.add_other_pid(other_pid)
    return doc


def _add_html(doc, files):
    for f in files:
        doc.add_html(language=f["lang"], uri=None)


def _add_pdf(doc, files):
    for f in files:
        doc.add_pdf(
            lang=f["lang"], url=f["uri"], filename=f["original_name"], type="pdf"
        )


def _add_mat_suppl(doc, files):
    doc.add_mat_suppl(
        lang=f["lang"],
        url=f["uri"],
        filename=f["original_name"],
        ref_id=f["id"],
    )


def _add_main_metadata(doc, xmltree):
    xml_article_titles = ArticleTitles(xmltree)
    article_title = xml_article_titles.article_title["text"]

    root = ArticleAndSubArticles(xmltree)
    main_lang = root.main_lang

    abstracts = Abstract(xmltree)
    try:
        main_abstract = abstracts.main_abstract
    except AttributeError:
        main_abstract = None

    xml_doi = DoiWithLang(xmltree)
    main_doi = xml_doi.main_doi

    xml_toc_section = ArticleTocSections(xmltree)
    try:
        section = xml_toc_section.article_section[0]["text"]
    except IndexError:
        section = None

    # TODO Abstract
    doc.add_document_type(root.main_article_type)
    doc.add_main_metadata(
        title=article_title,
        section=section,
        abstract=main_abstract,
        lang=root.main_lang,
        doi=xml_doi.main_doi,
    )


def _add_publication_date(doc, xmltree):
    xml_article_dates = ArticleDates(xmltree)
    date = xml_article_dates.article_date
    month = date.get("month")
    if month:
        date["month"] = date["month"].zfill(2)
    day = date.get("day")
    if day:
        date["day"] = date["day"].zfill(2)
    doc.add_publication_date(**date)


def _add_in_issue(doc, xmltree):
    aids = ArticleIds(xmltree)
    article_meta_issue = ArticleMetaIssue(xmltree)
    doc.add_in_issue(
        order=aids.other,
        fpage=article_meta_issue.fpage,
        fpage_seq=article_meta_issue.fpage_seq,
        lpage=article_meta_issue.lpage,
        elocation=article_meta_issue.elocation_id,
    )


def _add_author(doc, xmltree):
    for item in Authors(xmltree).contribs:
        affiliation = ", ".join(
            [a.get("original") or a.get("orgname") for a in item["affs"]]
        )
        doc.add_author(
            surname=item["surname"],
            given_names=item["given_names"],
            suffix=item["suffix"],
            affiliation=item["surname"],
            orcid=item.get("orcid"),
        )


def _add_translated_title(doc, xmltree):
    xml_article_titles = ArticleTitles(xmltree)
    for item in xml_article_titles.article_title_list[1:]:
        doc.add_translated_title(item["lang"], item["text"])


def _add_section(doc, xmltree):
    xml_toc_sections = ArticleTocSections(xmltree)
    for item in xml_toc_sections.article_section:
        doc.add_section(item["lang"], item["text"])
    for item in xml_toc_sections.sub_article_section:
        doc.add_section(item["lang"], item["text"])


def _add_abstract(doc, xmltree):
    # TODO doc.add_abstract(language, text)
    pass


def _add_keywords(doc, xmltree):
    for lang, keywords in KwdGroup(xmltree).extract_kwd_extract_data_by_lang.items():
        doc.add_keywords(lang, keywords)


def _add_doi_with_lang(doc, xmltree):
    doi_with_lang = DoiWithLang(xmltree)
    for item in doi_with_lang.data:
        doc.add_doi_with_lang(item["lang"], item["value"])


def _add_related_article(doc, xmltree):
    """
    <related-article ext-link-type="doi" id="A01"
    related-article-type="commentary-article"
    xlink:href="10.1590/0101-3173.2022.v45n1.p139">
    """
    related = RelatedItems(xmltree)

    for item in related.related_articles:
        try:
            registered = Article.objects.get(
                Q(doi__iexact=item["href"])
                | Q(doi_with_lang__doi__iexact=item["href"]),
            )
            ref_id = registered._id
        except Article.DoesNotExist:
            ref_id = None
        doc.add_related_article(
            doi=item["href"],
            ref_id=ref_id,
            related_type=item["related-article-type"],
        )
