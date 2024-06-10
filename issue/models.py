import logging

from django.conf import settings
from django.db import models, IntegrityError
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from wagtail.admin.panels import FieldPanel
from wagtailautocomplete.edit_handlers import AutocompletePanel

from core.models import CommonControlField, IssuePublicationDate
from journal.models import Journal

from .forms import IssueForm


class IssueGetOrCreateError(Exception):
    ...


class Issue(CommonControlField, IssuePublicationDate):
    """
    Class that represent Issue
    """

    def __unicode__(self):
        return "%s %s %s%s%s" % (
            self.journal,
            self.publication_year,
            self.volume and f"v{self.volume}",
            self.number and f"n{self.number}",
            self.supplement and f"s{self.supplement}",
        )

    def __str__(self):
        return "%s %s %s%s%s" % (
            self.journal,
            self.publication_year,
            self.volume and f"v{self.volume}",
            self.number and f"n{self.number}",
            self.supplement and f"s{self.supplement}",
        )

    journal = models.ForeignKey(
        Journal, on_delete=models.SET_NULL, null=True, blank=True
    )
    volume = models.CharField(_("Volume"), max_length=16, null=True, blank=True)
    number = models.CharField(_("Number"), max_length=16, null=True, blank=True)
    supplement = models.CharField(_("Supplement"), max_length=16, null=True, blank=True)
    publication_year = models.CharField(_("Year"), max_length=4, null=True, blank=True)

    @property
    def data(self):
        return dict(
            journal=self.journal.data,
            volume=self.volume,
            number=self.number,
            supplement=self.supplement,
            publication_year=self.publication_year,
            created=self.created.isoformat(),
            updated=self.updated.isoformat(),
        )

    @staticmethod
    def autocomplete_custom_queryset_filter(search_term):
        parts = search_term.split()
        if parts[-1].isdigit():
            return Issue.objects.filter(
                Q(journal__title__icontains=parts[0])
                | Q(publication_year__icontains=parts[-1])
            )
        return Issue.objects.filter(
            Q(journal__title__icontains=parts[0])
        )

    def autocomplete_label(self):
        return "%s %s%s%s" % (
            self.journal,
            self.volume and f"v{self.volume}",
            self.number and f"n{self.number}",
            self.supplement and f"s{self.supplement}",
        )

    panels = [
        AutocompletePanel("journal"),
        FieldPanel("publication_year"),
        FieldPanel("volume"),
        FieldPanel("number"),
        FieldPanel("supplement"),
    ]

    base_form_class = IssueForm

    class Meta:
        unique_together = [
            ["journal", "publication_year", "volume", "number", "supplement"],
            ["journal", "volume", "number", "supplement"],
        ]
        indexes = [
            models.Index(fields=["journal"]),
            models.Index(fields=["publication_year"]),
            models.Index(fields=["volume"]),
            models.Index(fields=["number"]),
            models.Index(fields=["supplement"]),
        ]

    @classmethod
    def get(cls, journal, volume, supplement, number):
        try:
            return cls.objects.get(
                journal=journal,
                volume=volume,
                supplement=supplement,
                number=number,
            )
        except cls.MultipleObjectsReturned:
            return cls.objects.filter(
                journal=journal,
                volume=volume,
                supplement=supplement,
                number=number,
            ).first()

    @classmethod
    def create(cls, user, journal, volume, supplement, number, publication_year):
        try:
            obj = cls()
            obj.journal = journal
            obj.volume = volume
            obj.supplement = supplement
            obj.number = number
            obj.publication_year = publication_year
            obj.creator = user
            obj.save()
            return obj
        except IntegrityError:
            return cls.get(
                journal, volume, supplement, number
            )
        except Exception as e:
            data = dict(
                journal=journal,
                volume=volume,
                supplement=supplement,
                number=number,
                publication_year=publication_year,
                user=user,
            )
            raise IssueGetOrCreateError(f"Unable to get or create issue {e} {data}")

    @classmethod
    def get_or_create(cls, journal, volume, supplement, number, publication_year, user):
        try:
            return cls.get(
                journal=journal,
                volume=volume,
                supplement=supplement,
                number=number,
            )
        except cls.DoesNotExist:
            return cls.create(
                user,
                journal, volume, supplement, number, publication_year
            )

    @staticmethod
    def exists(journal, volume, suppl, number, user):
        if not any((volume, number)):
            return
        try:
            return Issue.get(
                journal=journal,
                volume=volume,
                supplement=supplement,
                number=number,
            )
        except Issue.DoesNotExist:
            return Issue.fetch_and_create_issue(journal, volume, suppl, number, user)

    @staticmethod
    def fetch_and_create_issue(journal, volume, suppl, number, user):
        if journal and any((volume, number)):
            issn_print = journal.official_journal.issn_print
            issn_electronic = journal.official_journal.issn_electronic
            try:
                response = fetch_data(
                    url=settings.ISSUE_API_URL,
                    params={
                        "issn_print": issn_print,
                        "issn_electronic": issn_electronic,
                        "number": number,
                        "supplement": suppl,
                        "volume": volume,
                    },
                    json=True,
                )

            except Exception as e:
                logging.exception(e)
                return

            for issue in response.get("results"):
                official_journal = OfficialJournal.get(
                    issn_electronic=issue["issn_electronic"],
                    issn_print=issue["issn_print"],
                    issnl=issue["issn_issnl"],
                )
                journal = Journal.get(official_journal=official_journal)
                issue = Issue.get_or_create(
                    journal=journal,
                    volume=issue["volume"],
                    supplement=issue["supplement"],
                    number=issue["number"],
                    publication_year=issue["year"],
                    user=user,
                )
                return issue
