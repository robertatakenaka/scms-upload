import logging

from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import IntegrityError
from django.utils.translation import gettext_lazy as _
from wagtail.admin.panels import FieldPanel, InlinePanel
from wagtailautocomplete.edit_handlers import AutocompletePanel

from collection import choices
from collection.models import WebSiteConfiguration
from core.choices import LANGUAGE
from core.forms import CoreAdminModelForm
from core.models import CommonControlField
from journal.models import Journal
from issue.models import Issue
from article.models import Article
from publication.api.document import publish_article
from publication.api.issue import publish_issue
from publication.api.journal import publish_journal


class PublicationStatus(CommonControlField):
    uri = models.URLField(_("URI"), max_length=16, null=True, blank=True, unique=True)
    status = models.CharField(_("status"), max_length=10, null=True, blank=True)
    panels = [
        FieldPanel("uri"),
        FieldPanel("status"),
    ]

    class Meta:
        verbose_name = _("Publication status")
        verbose_name_plural = _("Publication status")

    def __str__(self):
        return f"{self.status} {self.uri}"

    @classmethod
    def create(cls, user, uri, status):
        try:
            obj = cls()
            obj.uri = uri
            obj.status = status
            obj.save()
            return obj
        except IntegrityError as e:
            return cls.get(uri)

    @classmethod
    def get(cls, uri):
        return cls.objects.get(uri=uri)

    @classmethod
    def create_or_update(cls, user, uri, status):
        try:
            obj = cls.get(uri=uri)
            obj.status = status
            obj.save()
            return obj
        except cls.DoesNotExist:
            return cls.create(user, uri, status)


class BasePublication(CommonControlField):
    website = models.ForeignKey(
        WebSiteConfiguration, null=True, blank=True, on_delete=models.SET_NULL
    )
    uris = models.ManyToManyField(PublicationStatus)

    panels = [
        AutocompletePanel("website"),
        FieldPanel("uri"),
    ]

    class Meta:
        abstract = True

    def __str__(self):
        return f"{self.parent})"

    @classmethod
    def create(cls, user, parent, website, **kwargs):
        try:
            obj = cls()
            obj.parent = parent
            obj.website = website
            for k, v in kwargs.items():
                setattr(obj, k, v)
            obj.save()
            return obj
        except IntegrityError as e:
            return cls.get(parent, website)

    @classmethod
    def get(cls, parent, website):
        return cls.objects.get(parent=parent, website=website)

    @classmethod
    def create_or_update(cls, user, parent, website, **kwargs):
        try:
            obj = cls.get(parent, website)
            for k, v in kwargs.items():
                setattr(obj, k, v)
            obj.save()
            return obj
        except cls.DoesNotExist:
            return cls.create(user, parent, website, **kwargs)

    def add_uri(self, uri, status):
        self.uris.add(PublicationStatus.create_or_update(uri=uri, status=status))

    @property
    def is_published(self):
        # retorna True para pelo menos uma rota publicada
        return self.uris.filter(status="PUBLISHED").exists()


class JournalPublication(BasePublication):
    parent = models.ForeignKey(
        Journal, null=True, blank=True, on_delete=models.SET_NULL
    )
    pid = models.CharField(_("pid"), max_length=9, null=True, blank=True)
    acron = models.CharField(_("acron"), max_length=16, null=True, blank=True)

    class Meta:
        verbose_name = _("Journal publication status")
        verbose_name_plural = _("Journal publication status")
        unique_together = [("parent", "website")]

    def add_uris(self, status, delete=True):
        domain = self.website.domain
        if "http" not in domain:
            domain = f"https://{domain}"

        if delete:
            self.uris.delete()
        self.add_uri(
            f"{domain}/scielo.php?script=sci_serial&pid={self.pid}",
            status,
        )
        self.add_uri(
            f"{domain}/j/{self.acron}",
            status,
        )

    def publish(self):
        publish_journal(self.parent, self.acron, self.pid, self.website.get_api_parameters("journal"))


class IssuePublication(BasePublication):
    parent = models.ForeignKey(Issue, null=True, blank=True, on_delete=models.SET_NULL)
    pid = models.CharField(_("pid"), max_length=17, null=True, blank=True)
    journal_publication = models.ForeignKey(
        JournalPublication, null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        verbose_name = _("Issue publication status")
        verbose_name_plural = _("Issue publication status")
        unique_together = [("parent", "website")]

    @property
    def journal_acron(self):
        return self.journal_publication.acron

    def add_uris(self, status, delete=True):
        domain = self.website.domain
        if "http" not in domain:
            domain = f"https://{domain}"
        pid_v2 = self.parent.pid_v2
        pid_v3 = self.parent.pid_v3

        if delete:
            self.uris.delete()
        self.add_uri(
            f"{domain}/scielo.php?script=sci_issuetoc&pid={self.pid}",
            status,
        )
        self.add_uri(
            f"{domain}/j/{self.journal_acron}/i/{self.parent.publication_year}.{self.issue_label}",
            status,
        )

    def publish(self):
        if not self.journal_publication.is_published:
            self.journal_publication.publish()

        publish_issue(
            self.parent, self.pid,
            self.parent.get_order(), self.parent.issue_label,
            self.website.get_api_parameters("issue")
        )


class ArticlePublication(BasePublication):
    parent = models.ForeignKey(
        Article, null=True, blank=True, on_delete=models.SET_NULL
    )
    journal_publication = models.ForeignKey(
        JournalPublication, null=True, blank=True, on_delete=models.SET_NULL
    )
    issue_publication = models.ForeignKey(
        IssuePublication, null=True, blank=True, on_delete=models.SET_NULL
    )

    class Meta:
        verbose_name = _("Article publication status")
        verbose_name_plural = _("Article publication status")
        unique_together = [("parent", "website")]

    @property
    def journal_pid(self):
        return self.journal_publication.pid

    @property
    def journal_acron(self):
        return self.journal_publication.acron

    def add_uris(self, status, delete=True):
        domain = self.website.domain
        if "http" not in domain:
            domain = f"https://{domain}"
        pid_v2 = self.parent.pid_v2
        pid_v3 = self.parent.pid_v3

        if delete:
            self.uris.delete()
        for item in self.parent.sections:
            lang = item.language
            self.add_uri(
                f"{domain}/scielo.php?script=sci_arttext&pid={pid_v2}&lang={lang}",
                status,
            )
            self.add_uri(
                f"{domain}/j/{self.journal_acron}/a/{pid_v3}/?lang={lang}",
                status,
            )

        for item in self.parent.sps_pkg.components.filter(component_type="rendition"):
            lang = item.lang
            self.add_uri(
                f"{domain}/scielo.php?script=sci_pdf&pid={pid_v2}&lang={lang}", status
            )
            self.add_uri(f"{domain}/{item.legacy_uri}", status)
            self.add_uri(
                f"{domain}/j/{self.journal_acron}/a/{pid_v3}/?format=pdf&lang={lang}",
                status,
            )

    def publish(self):
        if not self.journal_publication.is_published:
            self.journal_publication.publish()
        if not self.issue_publication.is_published:
            self.issue_publication.publish()
        publish_article(
            self.parent, self.journal_pid, self.website.get_api_parameters("article")
        )
