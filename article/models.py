from datetime import datetime

from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from wagtail.admin.panels import FieldPanel, InlinePanel, MultiFieldPanel
from wagtail.fields import RichTextField
from wagtail.models import Orderable
from wagtailautocomplete.edit_handlers import AutocompletePanel

from collection import choices as collection_choices
from collection.models import Collection
from core.models import CommonControlField
from doi.models import DOIWithLang
from issue.models import Issue
from journal.models import Journal, OfficialJournal, SciELOJournal
from package.models import SPSPkg
from researcher.models import Researcher

from . import choices
from .forms import ArticleForm, RelatedItemForm, RequestArticleChangeForm
from .permission_helper import MAKE_ARTICLE_CHANGE, REQUEST_ARTICLE_CHANGE

User = get_user_model()


class SciELOArticle(CommonControlField):
    # Armazena os IDs dos artigos no contexto de cada coleção
    # serve para conseguir recuperar artigos pelo ID do site clássico
    collection = models.ForeignKey(
        Collection, on_delete=models.SET_NULL, null=True, blank=True
    )
    article = models.ForeignKey(
        "Article", on_delete=models.SET_NULL, null=True, blank=True
    )
    publication_stage = models.CharField(
        _("Publication stage"),
        max_length=16,
        null=True,
        blank=True,
        choices=collection_choices.WS_PUBLICATION_STAGE,
    )

    @classmethod
    def get(cls, article=None, collection=None):
        return cls.objects.get(article=article, collection=collection)

    @classmethod
    def create_or_update(
        cls,
        user=None,
        article=None,
        collection=None,
        publication_stage=None,
    ):
        try:
            obj = cls.get(article=article, collection=collection)
            obj.updated_by = user
            obj.publication_stage = None
        except cls.DoesNotExist:
            obj = cls()
            obj.creator = user
            obj.collection = collection or obj.collection
            obj.article = article or obj.article
        obj.publication_stage = publication_stage or obj.publication_stage
        obj.save()
        return obj

    @classmethod
    def items_to_publish(cls, website_kind):
        if website_kind == collection_choices.QA:
            # seleciona journals para publicar em QA
            return cls.objects.filter(publication_stage__isnull=True).iterator()

        # seleciona itens para publicar em produção
        return cls.objects.filter(
            publication_stage=collection_choices.WS_APPROVED
        ).iterator()

    def update_publication_stage(self):
        if self.publication_stage == collection_choices.WS_APPROVED:
            # indica que foi publicado
            self.publication_stage = collection_choices.WS_PUBLISHED
        elif self.publication_stage is None:
            if self.article.sps_pkg.is_migrated:
                # indica que já está aprovado e deve ser publicado
                self.publication_stage = collection_choices.WS_APPROVED
            else:
                # indica que deve ser avaliado e aprovado para ser publicado
                self.publication_stage = collection_choices.WS_QA


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

    panel_article_ids = MultiFieldPanel(
        heading="Article identifiers", classname="collapsible"
    )
    panel_article_ids.children = [
        # FieldPanel("pid_v2"),
        FieldPanel("pid_v3"),
        # FieldPanel("aop_pid"),
        InlinePanel(relation_name="doi_with_lang", label="DOI with Language"),
    ]

    panel_article_details = MultiFieldPanel(
        heading="Article details", classname="collapsible"
    )
    panel_article_details.children = [
        FieldPanel("article_type"),
        FieldPanel("status"),
        InlinePanel(relation_name="title_with_lang", label="Title with Language"),
        InlinePanel(relation_name="author", label="Authors"),
        FieldPanel("elocation_id"),
        FieldPanel("fpage"),
        FieldPanel("lpage"),
    ]

    panels = [
        panel_article_ids,
        panel_article_details,
        FieldPanel("issue", classname="collapsible"),
    ]

    class Meta:
        permissions = (
            (MAKE_ARTICLE_CHANGE, _("Can make article change")),
            (REQUEST_ARTICLE_CHANGE, _("Can request article change")),
        )

    base_form_class = ArticleForm

    autocomplete_search_field = "pid_v3"

    def autocomplete_label(self):
        return self.pid_v3

    def __str__(self):
        return f"{self.pid_v3}"

    @classmethod
    def get(cls, pid_v3):
        if pid_v3:
            return cls.objects.get(pid_v3=pid_v3)
        raise ValueError("Article.get requires pid_v3")

    @classmethod
    def create_or_update(cls, user, sps_pkg):
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
        obj.save()

        for journal in SciELOJournal.objects.filter(journal=obj.journal).iterator():
            SciELOArticle.create_or_update(
                user=user,
                collection=journal.collection,
                article=obj,
            )
        return obj

    def complete_data(self, user):
        self.add_journal()
        self.add_issue()
        # ...
        article.save()

    def add_type(self, article_type):
        self.article_type = article_type

    def add_related_item(self, target_doi, target_article_type):
        self.save()
        # TODO
        # item = RelatedItem()
        # item.item_type = target_article_type
        # item.source_article = self
        # item.target_article = target_location
        # item.save()
        # self.related_items.add(item)

    def add_pages(self, fpage=None, fpage_seq=None, lpage=None, elocation_id=None):
        self.fpage = fpage
        self.fpage_seq = fpage_seq
        self.lpage = lpage
        self.elocation_id = elocation_id

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


class ArticleAuthor(Orderable, Researcher):
    author = ParentalKey("Article", on_delete=models.CASCADE, related_name="author")


class ArticleDOIWithLang(Orderable, DOIWithLang):
    doi_with_lang = ParentalKey(
        "Article", on_delete=models.CASCADE, related_name="doi_with_lang"
    )


class Title(CommonControlField):
    title = models.TextField(_("Title"))
    lang = models.CharField(_("Language"), max_length=64)

    panels = [
        FieldPanel("title"),
        FieldPanel("lang"),
    ]

    def __str__(self):
        return f"{self.lang.upper()}: {self.title}"

    class Meta:
        abstract = True


class ArticleTitle(Orderable, Title):
    title_with_lang = ParentalKey(
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
