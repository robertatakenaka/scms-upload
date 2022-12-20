from django.utils.translation import gettext as _

from lxml import etree
import requests

import hashlib
import logging
import os
from zipfile import ZipFile, BadZipFile
from shutil import copyfile
from tempfile import mkdtemp

from django.utils.translation import gettext as _

from lxml import etree

from packtools.sps.models.article_ids import ArticleIds
from packtools.sps.models.article_doi_with_lang import DoiWithLang
from packtools.sps.models.front_journal_meta import ISSN
from packtools.sps.models.front_articlemeta_issue import ArticleMetaIssue
from packtools.sps.models.article_authors import Authors
from packtools.sps.models.article_titles import ArticleTitles
from packtools.sps.models.body import Body
from packtools.sps.models.dates import ArticleDates
from packtools.sps.models.related_articles import RelatedItems


LOGGER = logging.getLogger(__name__)
LOGGER_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


class GetXmlWithPreError(Exception):
    ...


class GetXmlWithPreFromURIError(Exception):
    ...


def get_xml_items(xml_sps_file_path, filenames=None):
    """
    Get XML items from XML file or Zip file

    Arguments
    ---------
        xml_sps_file_path: str

    Return
    ------
    dict
    """
    name, ext = os.path.splitext(xml_sps_file_path)
    try:
        if ext == ".zip":
            return get_xml_items_from_zip_file(xml_sps_file_path, filenames)
        if ext == ".xml":
            xml = get_xml_from_xml_file(xml_sps_file_path)
            item = os.path.basename(xml_sps_file_path)
            yield {"filename": item, "xml": xml}

    except Exception as e:
        raise GetXMLItemsError(
            _("Unable to get xml items from {}: {} {}").format(
                xml_sps_file_path, type(e), e)
        )


def get_xml_items_from_zip_file(xml_sps_file_path, filenames=None):
    """
    Return the first XML content in the Zip file.

    Arguments
    ---------
        xml_sps_file_path: str
        content: bytes

    Return
    ------
    str
    """
    try:
        filenames = filenames or []
        with ZipFile(xml_sps_file_path) as zf:
            for item in filenames or zf.namelist():
                if item.endswith(".xml"):
                    try:
                        yield {
                            "filename": item,
                            "xml_with_pre": get_xml_with_pre(zf.read(item).decode("utf-8")),
                        }
                    except GetXmlWithPreError as e:
                        raise GetXMLItemsFromZipFileError(
                            _("Unable to get xml {} from zip file {}: {} {}").format(
                                item, xml_sps_file_path, type(e), e)
                        )
    except Exception as e:
        raise GetXMLItemsFromZipFileError(
            _("Unable to get xml items from zip file {}: {} {}").format(
                xml_sps_file_path, type(e), e)
        )


def update_zip_file_xml(xml_sps_file_path, xml_file_path, content):
    """
    Save XML content in a Zip file.
    Return saved zip file path

    Arguments
    ---------
        xml_sps_file_path: str
        content: bytes

    Return
    ------
    str
    """
    with ZipFile(xml_sps_file_path, "w") as zf:
        LOGGER.debug("Try to write xml %s %s %s" %
                     (xml_sps_file_path, xml_file_path, content[:100]))
        zf.writestr(xml_file_path, content)

    return os.path.isfile(xml_sps_file_path)


def create_xml_zip_file(xml_sps_file_path, content):
    """
    Save XML content in a Zip file.
    Return saved zip file path

    Arguments
    ---------
        xml_sps_file_path: str
        content: bytes

    Return
    ------
    str
    """
    dirname = os.path.dirname(xml_sps_file_path)
    if dirname and not os.path.isdir(dirname):
        os.makedirs(dirname)

    basename = os.path.basename(xml_sps_file_path)
    name, ext = os.path.splitext(basename)

    with ZipFile(xml_sps_file_path, "w") as zf:
        zf.writestr(name + ".xml", content)
    return os.path.isfile(xml_sps_file_path)


def get_xml_with_pre_from_uri(uri, timeout=30):
    try:
        response = requests.get(uri, timeout=timeout)
        xml_content = response.content.decode("utf-8")
    except Exception as e:
        raise GetXmlWithPreFromURIError(
            _("Unable to get xml from {}").format(uri)
        )
    return get_xml_with_pre(xml_content)


def get_xml_with_pre(xml_content):
    try:
        # return etree.fromstring(xml_content)
        pref, xml = split_processing_instruction_doctype_declaration_and_xml(
            xml_content
        )
        return XMLWithPre(pref, etree.fromstring(xml))

    except Exception as e:
        raise GetXmlWithPreError(e)


def split_processing_instruction_doctype_declaration_and_xml(xml_content):
    xml_content = xml_content.strip()

    p = xml_content.rfind("</")
    endtag = xml_content[p:]
    starttag = endtag.replace("/", "").replace(">", "").strip()

    p = xml_content.find(starttag)
    return xml_content[:p], xml_content[p:].strip()


class XMLWithPre:
    """
    Preserva o texto anterior ao elemento `root`
    """

    def __init__(self, xmlpre, xmltree):
        self.xmlpre = xmlpre or ''
        self.xmltree = xmltree

    def tostring(self):
        return (
            self.xmlpre +
            etree.tostring(self.xmltree, encoding="utf-8").decode("utf-8")
        )

    def update_ids(self, v3, v2, aop_pid):
        # update IDs
        self.article_ids.v3 = v3
        self.article_ids.v2 = v2
        if aop_pid:
            self.article_ids.aop_pid = aop_pid

    @property
    def related_items(self):
        if not hasattr(self, '_related_items') or not self._related_items:
            # list of dict which keys are
            # href, ext-link-type, related-article-type
            items = RelatedItems(self.xmltree)
            self._related_items = list(items.related_articles)
        return self._related_items

    @property
    def article_ids(self):
        if not hasattr(self, '_article_ids') or not self._article_ids:
            # [{"lang": "en", "value": "DOI"}]
            self._article_ids = ArticleIds(self.xmltree)
        return self._article_ids

    @property
    def v3(self):
        return self.article_ids.v3

    @property
    def v2(self):
        return self.article_ids.v2

    @property
    def aop_pid(self):
        return self.article_ids.aop_pid

    @v3.setter
    def v3(self, value):
        self.article_ids.v3 = value

    @v2.setter
    def v2(self, value):
        self.article_ids.v2 = value

    @aop_pid.setter
    def aop_pid(self, value):
        self.article_ids.aop_pid = value

    @property
    def article_doi_with_lang(self):
        if not hasattr(self, '_article_doi_with_lang') or not self._article_doi_with_lang:
            # [{"lang": "en", "value": "DOI"}]
            doi_with_lang = DoiWithLang(self.xmltree)
            self._main_doi = doi_with_lang.main_doi
            self._article_doi_with_lang = doi_with_lang.data
        return self._article_doi_with_lang

    @property
    def main_doi(self):
        if not hasattr(self, '_main_doi') or not self._main_doi:
            # [{"lang": "en", "value": "DOI"}]
            doi_with_lang = DoiWithLang(self.xmltree)
            self._main_doi = doi_with_lang.main_doi
        return self._main_doi

    @property
    def issns(self):
        if not hasattr(self, '_issns') or not self._issns:
            # [{"type": "epub", "value": "1234-9876"}]
            issns = ISSN(self.xmltree)
            self._issns = issns.data
        return self._issns

    @property
    def is_aop(self):
        if not hasattr(self, '_is_aop') or not self._is_aop:
            items = (
                self.article_in_issue['volume'],
                self.article_in_issue['number'],
                self.article_in_issue['suppl'],
            )
            self._is_aop = not any(items)
        return self._is_aop

    @property
    def article_in_issue(self):
        if not hasattr(self, '_article_in_issue') or not self._article_in_issue:
            _data = {
                k: '' for k in (
                    "volume", "number", "suppl",
                    "fpage", "fpage_seq", "lpage",
                    "pub_year",
                )
            }
            article_in_issue = ArticleMetaIssue(self.xmltree)
            _data.update(article_in_issue.data)
            if not _data.get("pub_year"):
                _data["pub_year"] = ArticleDates(
                    self.xmltree).article_date["year"]

            if _data.get("pub_year"):
                _data["pub_year"] = int(_data["pub_year"])

            self._article_in_issue = _data
        return self._article_in_issue

    @property
    def authors(self):
        if not hasattr(self, '_authors') or not self._authors:
            authors = Authors(self.xmltree)
            self._authors = {
                "person": authors.contribs,
                "collab": authors.collab or None,
            }
        return self._authors

    @property
    def article_titles(self):
        if not hasattr(self, '_article_titles') or not self._article_titles:
            # list of dict which keys are lang and text
            article_titles = ArticleTitles(self.xmltree)
            self._article_titles = article_titles.data
        return self._article_titles

    @property
    def partial_body(self):
        if not hasattr(self, '_partial_body') or not self._partial_body:
            try:
                body = Body(self.xmltree)
                for text in body.main_body_texts:
                    if text:
                        self._partial_body = text
                        break
            except AttributeError:
                self._partial_body = None
        return self._partial_body

    @property
    def collab(self):
        if not hasattr(self, '_collab') or not self._collab:
            self._collab = self.authors.get("collab")
        return self._collab

    @property
    def journal(self):
        if not hasattr(self, '_journal') or not self._journal:
            # [{"type": "epub", "value": "1234-9876"}]
            journal = ISSN(self.xmltree)
            self._journal = {
                item['type']: item['value']
                for item in self.issns
            }
        return self._journal
