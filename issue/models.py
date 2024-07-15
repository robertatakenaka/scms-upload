import logging

from django.db import IntegrityError, models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from wagtail.admin.panels import FieldPanel, InlinePanel
from wagtailautocomplete.edit_handlers import AutocompletePanel
from wagtail.models import Orderable

from core.models import CommonControlField, IssuePublicationDate
from journal.models import Journal, JournalSection

from issue.forms import IssueForm, TOCForm


def _get_digits(value):
    d = "".join([c for c in value if c.isdigit()])
    try:
        return int(d)
    except ValueError:
        return 0


class IssueGetOrCreateError(Exception):
    ...


class Issue(CommonControlField, IssuePublicationDate):
    """
    Class that represent Issue
    """

    journal = models.ForeignKey(
        Journal, on_delete=models.SET_NULL, null=True, blank=True
    )
    volume = models.CharField(_("Volume"), max_length=16, null=True, blank=True)
    number = models.CharField(_("Number"), max_length=16, null=True, blank=True)
    supplement = models.CharField(_("Supplement"), max_length=16, null=True, blank=True)
    publication_year = models.CharField(_("Year"), max_length=4, null=True, blank=True)
    total_documents = models.PositiveSmallIntegerField(null=True, blank=True)
    is_continuous_publishing_model = models.BooleanField(null=True, blank=True)
    order = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text=_("This number controls the order issues appear for a specific year on the website grid"))

    def __unicode__(self):
        return "%s %s" % (
            self.journal,
            self.issue_folder,
        )

    def __str__(self):
        return "%s %s" % (
            self.journal,
            self.issue_folder,
        )

    @property
    def issue_folder(self):
        labels = [(self.volume, "v"), (self.number, "n"), (self.supplement, "s")]
        return "".join([f"{prefix}{value}" for value, prefix in labels if value])

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
        return Issue.objects.filter(Q(journal__title__icontains=parts[0]))

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
        FieldPanel("is_continuous_publishing_model"),
        FieldPanel("total_documents"),
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
    def create(
        cls,
        user,
        journal,
        volume,
        supplement,
        number,
        publication_year,
        is_continuous_publishing_model=None,
        total_documents=None,
    ):
        try:
            obj = cls()
            obj.journal = journal
            obj.volume = volume
            obj.supplement = supplement
            obj.number = number
            obj.publication_year = publication_year
            obj.order = obj.generate_order()
            obj.is_continuous_publishing_model = is_continuous_publishing_model
            obj.total_documents = total_documents
            obj.creator = user
            obj.save()
            return obj
        except IntegrityError:
            return cls.get(journal, volume, supplement, number)
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
    def get_or_create(
        cls,
        journal,
        volume,
        supplement,
        number,
        publication_year,
        user,
        is_continuous_publishing_model=None,
        total_documents=None,
    ):
        try:
            obj = cls.get(
                journal=journal,
                volume=volume,
                supplement=supplement,
                number=number,
            )
            obj.is_continuous_publishing_model = is_continuous_publishing_model
            obj.total_documents = total_documents
            obj.publication_year = publication_year
            return obj
        except cls.DoesNotExist:
            return cls.create(
                user,
                journal,
                volume,
                supplement,
                number,
                publication_year,
                is_continuous_publishing_model,
                total_documents,
            )

    def generate_order(self, suppl_start=1000, spe_start=2000):
        x = 0
        if self.supplement is not None:
            x = suppl_start
            try:
                suppl = int(self.supplement)
            except (ValueError, TypeError):
                suppl = _get_digits(self.supplement)
            return x + suppl

        number = self.number
        if not number:
            return 1

        spe = None
        if "spe" in number:
            x = spe_start
            parts = number.split("spe")
            spe = int(parts[-1] or 0)
            return x + spe
        elif number == "ahead":
            return 9999

        try:
            number = int(number)
        except (ValueError, TypeError):
            number = _get_digits(number)
        return number or 1

    @staticmethod
    def exists(journal, volume, suppl, number, user):
        if not any((volume, number)):
            return
        try:
            return Issue.get(
                journal=journal,
                volume=volume,
                supplement=suppl,
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
                issue = Issue.get_or_create(
                    journal=journal,
                    volume=issue["volume"],
                    supplement=issue["supplement"],
                    number=issue["number"],
                    publication_year=issue["year"],
                    user=user,
                )
                # TODO dados das coleções pid
                return issue


class TOC(CommonControlField, ClusterableModel):
    # Somente para issues cujos artigos não tem página numérica
    issue = models.ForeignKey(Issue, blank=True, null=True, on_delete=models.SET_NULL)
    ordered = models.BooleanField(default=False)

    panels = [
        InlinePanel("issue_sections", label=_("Sections")),
    ]

    base_form_class = TOCForm

    @classmethod
    def create(cls, user, issue, ordered):
        try:
            obj = cls(creator=user, issue=issue, ordered=ordered)
            obj.save()
            return obj
        except IntegrityError as e:
            return cls.get(issue)

    @classmethod
    def create_or_update(cls, user, issue, ordered):
        try:
            obj = cls.get(issue)
            obj.ordered = ordered
            obj.save()
            return obj
        except cls.DoesNotExist:
            return cls.create(user, issue, ordered)

    @classmethod
    def get(cls, issue):
        return cls.objects.get(issue=issue)

    @property
    def ordered_sections(self):
        sections = {}
        for item in IssueSection.objects.filter(toc=self):
            sections.setdefault(item["order"], [])
            sections[item["order"]].append(item)
        return sections


class IssueSection(CommonControlField, Orderable):
    toc = ParentalKey(TOC, on_delete=models.CASCADE, related_name="issue_sections")
    main_section = models.ForeignKey(JournalSection, null=True, blank=True, on_delete=models.SET_NULL, related_name="main_section_toc")
    translations = models.ManyToManyField(JournalSection, related_name="translated_section_toc")
    position = models.PositiveSmallIntegerField(_("Position"), blank=True, null=True)

    panels = [
        AutocompletePanel("main_section"),
        AutocompletePanel("translations"),
    ]

    class Meta:
        ordering = ["position"]

    @classmethod
    def create(cls, user, toc, main_section):
        try:
            obj = cls(creator=user, toc=toc, main_section=main_section)
            obj.save()
            return obj
        except IntegrityError as e:
            return cls.get(toc, main_section)

    @classmethod
    def create_or_update(cls, user, toc, main_section):
        try:
            obj = cls.get(toc, main_section)
            obj.save()
            return obj
        except cls.DoesNotExist:
            return cls.create(user, toc, main_section)

    @classmethod
    def get(cls, toc, main_section):
        return cls.objects.get(toc=toc, main_section=main_section)

    @property
    def data(self):
        yield self.main_section.data
        for item in self.translations.all():
            yield item.data
