import hashlib
import logging

from django.utils.translation import gettext as _


LOGGER = logging.getLogger(__name__)
LOGGER_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


class XMLAdapter:

    def __init__(self, xml_with_pre):
        self.xml_with_pre = xml_with_pre

    def __getattr__(self, name):
        # try:
        #     return getattr(self, name)
        # except:
        try:
            return getattr(self.xml_with_pre, name)
        except:
            raise AttributeError(f"XMLAdapter.{name} does not exist")

    # def tostring(self):
    #     return self.xml_with_pre.tostring()

    @property
    def v2_prefix(self):
        return f"S{self.journal_issn_electronic or self.journal_issn_print}{self.issue['pub_year']}"

    @property
    def journal_issn_print(self):
        if not hasattr(self, '_journal_issn_print') or not self._journal_issn_print:
            # list of dict which keys are
            # href, ext-link-type, related-article-type
            self._journal_issn_print = self.journal.get("ppub")
        return self._journal_issn_print

    @property
    def journal_issn_electronic(self):
        if not hasattr(self, '_journal_issn_electronic') or not self._journal_issn_electronic:
            # list of dict which keys are
            # href, ext-link-type, related-article-type
            self._journal_issn_electronic = self.journal.get("epub")
        return self._journal_issn_electronic

    @property
    def links(self):
        if not hasattr(self, '_links') or not self._links:
            # list of dict which keys are
            # href, ext-link-type, related-article-type
            self._links = _str_with_64_char(
                "|".join([item['href'] for item in self.xml_with_pre.related_items])
                )
        return self._links

    @property
    def related_items(self):
        if not hasattr(self, '_related_items') or not self._related_items:
            # list of dict which keys are
            # href, ext-link-type, related-article-type
            self._related_items = [
                item['href']
                for item in self.xml_with_pre.related_items
            ]
        return self._related_items

    @property
    def main_doi(self):
        if not hasattr(self, '_main_doi') or not self._main_doi:
            self._main_doi = _str_with_64_char(self.xml_with_pre.main_doi)
        return self._main_doi

    @property
    def collab(self):
        if not hasattr(self, '_collab') or not self._collab:
            self._collab = _str_with_64_char(self.xml_with_pre.collab)
        return self._collab

    @property
    def surnames(self):
        if not hasattr(self, '_surnames') or not self._surnames:
            self._surnames = _str_with_64_char(
                "|".join([
                    _standardize(person.get("surname"))
                    for person in self.authors.get("person")
                ]))
        return self._surnames

    @property
    def article_titles_texts(self):
        if not hasattr(self, '_article_titles_texts') or not self._article_titles_texts:
            self._article_titles_texts = _str_with_64_char(
                "|".join([
                    _standardize(item.get("text"))
                    for item in self.article_titles
                ]))
        return self._article_titles_texts

    @property
    def partial_body(self):
        if not hasattr(self, '_partial_body') or not self._partial_body:
            self._partial_body = _str_with_64_char(self.xml_with_pre.partial_body)
        return self._partial_body

    @property
    def pages(self):
        if not hasattr(self, '_pages') or not self._pages:
            self._pages = {
                k: self.xml_with_pre.article_in_issue.get(k)
                for k in (
                    "fpage", "fpage_seq", "lpage",
                )
            }
        return self._pages

    @property
    def elocation_id(self):
        if not hasattr(self, '_elocation_id') or not self._elocation_id:
            self._elocation_id = self.xml_with_pre.article_in_issue.get("elocation_id")
        return self._elocation_id

    @property
    def issue(self):
        if not hasattr(self, '_issue') or not self._issue:
            self._issue = {
                k: self.xml_with_pre.article_in_issue.get(k)
                for k in (
                    "volume", "number", "suppl", "pub_year",
                )
            }
            self._issue['pub_year'] = int(self._issue['pub_year'])
        return self._issue

    @property
    def article_publication_date(self):
        return self.xml_with_pre.article_publication_date


def _standardize(text):
    return (text or '').strip().upper()


def _str_with_64_char(text):
    """
    >>> import hashlib
    >>> m = hashlib.sha256()
    >>> m.update(b"Nobody inspects")
    >>> m.update(b" the spammish repetition")
    >>> m.digest()
    b'\x03\x1e\xdd}Ae\x15\x93\xc5\xfe\\\x00o\xa5u+7\xfd\xdf\xf7\xbcN\x84:\xa6\xaf\x0c\x95\x0fK\x94\x06'
    >>> m.digest_size
    32
    >>> m.block_size
    64
    hashlib.sha224(b"Nobody inspects the spammish repetition").hexdigest()
    """
    if not text:
        return None
    return hashlib.sha256(_standardize(text).encode("utf-8")).hexdigest()
