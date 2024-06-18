import logging
from datetime import datetime
from django.contrib.auth import get_user_model
from django.db import models, IntegrityError
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from packtools.sps.models.article_authors import Authors
from packtools.sps.models.article_titles import ArticleTitles
from packtools.sps.models.article_toc_sections import ArticleTocSections
from wagtail.fields import RichTextField
from wagtail.admin.panels import (
    FieldPanel,
    InlinePanel,
    MultiFieldPanel,
)
from wagtailautocomplete.edit_handlers import AutocompletePanel
from wagtail.models import Orderable

from collection.models import Language
from collection import choices as collection_choices
from core.models import CommonControlField, HTMLTextModel
from doi.models import DOIWithLang
from issue.models import Issue
from journal.models import Journal, OfficialJournal
from package.models import SPSPkg
from publication.tasks import task_publish_article
from researcher.models import Researcher

from . import choices
from .forms import (
    ArticleForm,
    RelatedItemForm,
    RequestArticleChangeForm,
    TOCForm,
    TOCSectionForm,
    ScheduledArticleModelForm,
)
from .permission_helper import MAKE_ARTICLE_CHANGE, REQUEST_ARTICLE_CHANGE

User = get_user_model()


class JournalSection(HTMLTextModel):
    parent = models.ForeignKey(Journal, blank=True, null=True, on_delete=models.SET_NULL)


class Article(ClusterableModel, CommonControlField):
    """
    No contexto de Upload, Article deve conter o mínimo de campos,
    suficiente para o processo de ingresso / validações,
    pois os dados devem ser obtidos do XML
    """

    sps_pkg = models.ForeignKey(
        SPSPkg, blank=True, null=True, on_delete=models.SET_NULL
    )
    # PID v3
    pid_v3 = models.CharField(_("PID v3"), max_length=23, blank=True, null=True)
    pid_v2 = models.CharField(_("PID v2"), max_length=23, blank=True, null=True)

    # Article type
    article_type = models.CharField(
        _("Article type"),
        max_length=32,
        choices=choices.ARTICLE_TYPE,
        blank=False,
        null=False,
    )

    # Article status
    status = models.CharField(
        _("Article status"),
        max_length=32,
        choices=choices.ARTICLE_STATUS,
        blank=True,
        null=True,
    )
    position = models.PositiveSmallIntegerField(_("Position"), blank=True, null=True)
    first_publication_date = models.DateField(auto_now=True, auto_now_add=False, null=True, blank=True)

    # Page
    elocation_id = models.CharField(
        _("Elocation ID"), max_length=64, blank=True, null=True
    )
    fpage = models.CharField(_("First page"), max_length=16, blank=True, null=True)
    lpage = models.CharField(_("Last page"), max_length=16, blank=True, null=True)

    # External models
    issue = models.ForeignKey(Issue, blank=True, null=True, on_delete=models.SET_NULL)
    journal = models.ForeignKey(
        Journal, blank=True, null=True, on_delete=models.SET_NULL
    )
    related_items = models.ManyToManyField(
        "self", symmetrical=False, through="RelatedItem", related_name="related_to"
    )

    # apenas para ajudar a identificar o artigo
    first_author = models.CharField(_("First author"), null=True, blank=True, max_length=265)

    sections = models.ManyToManyField(JournalSection, verbose_name=_("sections"))

    # panel_article_ids = MultiFieldPanel(
    #     heading="Article identifiers", classname="collapsible"
    # )
    # panel_article_ids.children = [
    #     # FieldPanel("pid_v2"),
    #     FieldPanel("pid_v3"),
    #     # FieldPanel("aop_pid"),
    #     InlinePanel(relation_name="doi_with_lang", label="DOI with Language"),
    # ]

    # panel_article_details = MultiFieldPanel(
    #     heading="Article details", classname="collapsible"
    # )
    # panel_article_details.children = [
    #     FieldPanel("article_type"),
    #     FieldPanel("status"),
    #     InlinePanel(relation_name="title_with_lang", label="Title with Language"),
    #     FieldPanel("first_author"),
    #     FieldPanel("elocation_id"),
    #     FieldPanel("fpage"),
    #     FieldPanel("lpage"),
    #     FieldPanel("first_publication_date"),
    # ]

    panels = [
        FieldPanel("journal", read_only=True),
        FieldPanel("issue", read_only=True),
        FieldPanel("first_publication_date"),
        FieldPanel("first_author", read_only=True),
        InlinePanel(relation_name="title_with_lang", label=_("Titles")),
    ]
    base_form_class = ArticleForm

    class Meta:
        indexes = [
            models.Index(fields=["pid_v3"]),
            models.Index(fields=["status"]),
        ]
        ordering = ['position', 'fpage', '-first_publication_date']

        permissions = (
            (MAKE_ARTICLE_CHANGE, _("Can make article change")),
            (REQUEST_ARTICLE_CHANGE, _("Can request article change")),
        )

    def __str__(self):
        try:
            return f"{self.title_with_lang[0]} {self.first_author}"
        except IndexError: 
            return self.sps_pkg.sps_pkg_name

    @classmethod
    def autocomplete_custom_queryset_filter(cls, term):
        return cls.objects.filter(
            Q(sps_pkg__sps_pkg_name__endswith=term) |
            Q(title_with_lang__title__icontains=term)
        )

    def autocomplete_label(self):
        return str(self)

    @property
    def pdfs(self):
        return self.sps_pkg.pdfs

    @property
    def htmls(self):
        return self.sps_pkg.htmls

    @property
    def xml(self):
        return self.sps_pkg.xml_uri

    @property
    def order(self):
        try:
            return int(self.fpage)
        except (TypeError, ValueError):
            return self.position

    @property
    def data(self):
        # TODO completar com itens que identifique o artigo
        return dict(
            xml=self.sps_pkg and self.sps_pkg.xml_uri,
            issue=self.issue.data,
            journal=self.journal.data,
            pid_v3=self.pid_v3,
            created=self.created.isoformat(),
            updated=self.updated.isoformat(),
        )

    @classmethod
    def get(cls, pid_v3):
        if pid_v3:
            return cls.objects.get(pid_v3=pid_v3)
        raise ValueError("Article.get requires pid_v3")

    @classmethod
    def create_or_update(cls, user, sps_pkg, issue=None, journal=None):
        if not sps_pkg or sps_pkg.pid_v3 is None:
            raise ValueError("create_article requires sps_pkg with pid_v3")

        try:
            obj = cls.get(sps_pkg.pid_v3)
            obj.updated_by = user
        except cls.DoesNotExist:
            obj = cls()
            obj.pid_v3 = sps_pkg.pid_v3
            obj.creator = user

        obj.sps_pkg = sps_pkg
        obj.pid_v2 = pid_v2
        obj.article_type = sps_pkg.xml_with_pre.xmltree.find(".").get("article_type")

        if journal:
            obj.journal = journal
        else:
            obj.add_journal(user)
        if issue:
            obj.issue = issue
        else:
            obj.add_issue(user)

        obj.status = choices.AS_READ_TO_PUBLISH
        obj.add_pages()
        obj.add_article_publication_date()
        obj.add_first_author()
        obj.save()

        obj.add_article_titles(user)
        return obj

    def add_related_item(self, target_doi, target_article_type):
        self.save()
        # TODO
        # item = RelatedItem()
        # item.item_type = target_article_type
        # item.source_article = self
        # item.target_article = target_location
        # item.save()
        # self.related_items.add(item)

    def add_article_publication_date(self):
        self.first_publication_date = datetime.strptime(
            self.sps_pkg.xml_with_pre.article_publication_date, "%Y-%m-%d")

    def add_pages(self):
        xml_with_pre = self.sps_pkg.xml_with_pre
        self.fpage = xml_with_pre.fpage
        self.fpage_seq = xml_with_pre.fpage_seq
        self.lpage = xml_with_pre.lpage
        self.elocation_id = xml_with_pre.elocation_id

    def add_issue(self, user):
        xml_with_pre = self.sps_pkg.xml_with_pre
        self.issue = Issue.get(
            journal=self.journal,
            volume=xml_with_pre.volume,
            supplement=xml_with_pre.suppl,
            number=xml_with_pre.number,
        )

    def add_journal(self, user):
        xml_with_pre = self.sps_pkg.xml_with_pre
        self.journal = Journal.get(
            official_journal=OfficialJournal.get(
                issn_electronic=xml_with_pre.journal_issn_electronic,
                issn_print=xml_with_pre.journal_issn_print,
            ),
        )

    def add_article_titles(self, user):
        titles = ArticleTitles(
            xmltree=self.sps_pkg.xml_with_pre.xmltree,
        ).article_title_list
        self.title_with_lang.delete()
        for title in titles:
            obj = ArticleTitle.create_or_update(
                user,
                parent=self,
                html_text=title.get("html_text"),
                plain_text=title.get("plain_text"),
                lang_code2=title.get("language") or title.get("lang"),
            )
            self.title_with_lang.add(obj)

    def add_sections(self, user):
        self.sections.delete()
        items = ArticleTocSections(
            xmltree=self.sps_pkg.xml_with_pre.xmltree,
        ).article_section
        for item in items:
            self.sections.add(
                JournalSection.create_or_update(
                    user,
                    parent=self.article.journal,
                    html_text=item.get("text"),
                    plain_text=item.get("text"),
                    lang_code2=item.get("lang"),
                )
            )

    def add_first_author(self):
        authors = Authors(xmltree=self.sps_pkg.xml_with_pre.xmltree).contribs_with_affs
        for author in authors:
            try:
                self.first_author = author["collab"]
            except KeyError:
                names = []
                for label in ("given_names", "surname", "suffix"):
                    try:
                        name = author[label].strip()
                        if name:
                            names.append(name)
                    except (ValueError, TypeError, KeyError):
                        pass
                if names:
                    self.first_author = " ".join(names)
            break

    def prepare_publication(self, user):
        if not self.first_publication_date:
            now = datetime.utcnow()
            self.first_publication_date = now
            self.save()

            self.sps_pkg.xml_with_pre.article_publication_date = {
                "year": now.year,
                "month": now.month,
                "day": now.day,
            }

        if not self.fpage:
            toc = TOC.create_or_update(user, self.issue)
            toc.add_article(self)
        else:
            self.publish(user, collection_choices.QA)

    def publish(self, user, website_kind):
        task_publish_article.apply_async(
            kwargs=dict(
                user_id=user.id,
                item_id=self.id,
                website_kind=website_kind,
            )
        )

    def change_status_to_submitted(self):
        if self.status in (choices.AS_REQUIRE_UPDATE, choices.AS_REQUIRE_ERRATUM):
            self.status = choices.AS_CHANGE_SUBMITTED
            self.save()
            return True
        else:
            return False


class ApprovedArticle(Article):

    panels = [
        FieldPanel("publication_date"),
    ]

    base_form_class = ApprovedArticleModelForm

    class Meta:
        proxy = True


class ArticleDOIWithLang(Orderable, DOIWithLang):
    doi_with_lang = ParentalKey(
        "Article", on_delete=models.CASCADE, related_name="doi_with_lang"
    )


class ArticleTitle(HTMLTextModel):
    """
    Represents an article title with text and language information.
    """
    parent = ParentalKey(
        "Article", on_delete=models.CASCADE, related_name="title_with_lang"
    )


class RelatedItem(CommonControlField):
    item_type = models.CharField(
        _("Related item type"),
        max_length=32,
        choices=choices.RELATED_ITEM_TYPE,
        blank=False,
        null=False,
    )
    source_article = models.ForeignKey(
        "Article",
        related_name="source_article",
        on_delete=models.CASCADE,
        null=False,
        blank=False,
    )
    target_article = models.ForeignKey(
        "Article",
        related_name="target_article",
        on_delete=models.CASCADE,
        null=False,
        blank=False,
    )

    panel = [
        FieldPanel("item_type"),
        FieldPanel("source_article"),
        FieldPanel("target_article"),
    ]

    def __str__(self):
        return f"{self.source_article} - {self.target_article} ({self.item_type})"

    base_form_class = RelatedItemForm


class RequestArticleChange(CommonControlField):
    deadline = models.DateField(_("Deadline"), blank=False, null=False)

    change_type = models.CharField(
        _("Change type"),
        max_length=32,
        choices=choices.REQUEST_CHANGE_TYPE,
        blank=False,
        null=False,
    )
    comment = RichTextField(_("Comment"), max_length=512, blank=True, null=True)

    article = models.ForeignKey(
        Article, on_delete=models.CASCADE, blank=True, null=True
    )
    pid_v3 = models.CharField(_("PID v3"), max_length=23, blank=True, null=True)
    demanded_user = models.ForeignKey(
        User, on_delete=models.CASCADE, blank=False, null=False
    )

    panels = [
        FieldPanel("pid_v3", classname="collapsible"),
        FieldPanel("deadline", classname="collapsible"),
        FieldPanel("change_type", classname="collapsible"),
        AutocompletePanel("demanded_user", classname="collapsible"),
        FieldPanel("comment", classname="collapsible"),
    ]

    def __str__(self) -> str:
        return f"{self.article or self.pid_v3} - {self.deadline}"

    base_form_class = RequestArticleChangeForm


class TOC(CommonControlField, ClusterableModel):
    issue = models.ForeignKey(Issue, blank=True, null=True, on_delete=models.SET_NULL)

    panels = [
        InlinePanel("toc_articles", label=_("Articles")),
    ]

    base_form_class = TOCForm

    class Meta:
        unique_together = [("issue", )]  # Redundant with 'text' unique=True

    @classmethod
    def create(cls, user, issue):
        try:
            obj = cls(creator=user, issue=issue)
            obj.save()
            return obj
        except IntegrityError as e:
            return cls.get(issue=issue)

    @classmethod
    def create_or_update(cls, user, issue):
        try:
            obj = cls.get(issue)
            obj.save()
            return obj
        except cls.DoesNotExist:
            return cls.create(user, issue)

    @classmethod
    def get(cls, issue):
        return cls.objects.get(issue=issue)


class SectionArticle(CommonControlField, Orderable):

    toc = ParentalKey(TOC, null=True, blank=True, on_delete=models.SET_NULL, related_name="toc_articles")
    article = models.ForeignKey(Article, null=True, blank=True, on_delete=models.SET_NULL)
    position = models.PositiveSmallIntegerField(_("Position"), blank=True, null=True)

    panels = [
        FieldPanel("position"),
        AutocompletePanel("article", label=_("Articles")),
    ]

    class Meta:
        unique_together = [("toc", "article")]  # Redundant with 'text' unique=True
        ordering = ("position", "-created", "-updated")


class MultilingualTOC(CommonControlField, ClusterableModel):
    issue = models.ForeignKey(Issue, blank=True, null=True, on_delete=models.SET_NULL)

    panels = [
        AutocompletePanel("issue"),
        InlinePanel("multilingual_sections", label=_("Sections")),
    ]

    base_form_class = MultilingualTOCForm

    class Meta:
        unique_together = [("issue", )]  # Redundant with 'text' unique=True

    @classmethod
    def create(cls, user, issue):
        try:
            obj = cls(creator=user, issue=issue)
            obj.save()
            return obj
        except IntegrityError as e:
            return cls.get(issue=issue)

    @classmethod
    def create_or_update(cls, user, issue):
        try:
            obj = cls.get(issue)
            obj.save()
            return obj
        except cls.DoesNotExist:
            return cls.create(user, issue)

    @classmethod
    def get(cls, issue):
        return cls.objects.get(issue=issue)


class MultilingualSection(CommonControlField, Orderable):

    toc = ParentalKey(MultilingualTOC, null=True, blank=True, on_delete=models.SET_NULL, related_name="multilingual_sections")
    main_section = models.ForeignKey(JournalSection, null=True, blank=True, on_delete=models.SET_NULL)
    translated_sections = models.ManyToManyField(JournalSection)

    panels = [
        AutocompletePanel("main_section"),
        AutocompletePanel("translated_sections", label=_("Translated sections")),
    ]

    class Meta:
        unique_together = [("toc", "main_section", )]  # Redundant with 'text' unique=True

    # @classmethod
    # def create(cls, user, toc, main_section=None):
    #     try:
    #         obj = cls(creator=user, toc=toc, main_section=main_section)
    #         obj.save()
    #         return obj
    #     except IntegrityError as e:
    #         return cls.get(toc=toc, main_section=main_section)

    # @classmethod
    # def create_or_update(cls, user, toc, main_section=None):
    #     try:
    #         obj = cls.get(toc, main_section)
    #         obj.save()
    #         return obj
    #     except cls.DoesNotExist:
    #         return cls.create(user, toc, main_section)

    # @classmethod
    # def get(cls, toc, main_section):
    #     return cls.objects.get(toc=toc, main_section=main_section)
