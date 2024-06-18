import logging
from datetime import datetime

from django.conf import settings
from django.db import models, IntegrityError
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from wagtail.admin.panels import FieldPanel, InlinePanel, TabbedInterface, ObjectList
from wagtail.models import Orderable
from wagtailautocomplete.edit_handlers import AutocompletePanel

from collection.models import Collection
from core.choices import MONTHS
from core.forms import CoreAdminModelForm
from core.models import CommonControlField, HTMLText
from core.utils.requester import fetch_data
from institution.models import InstitutionHistory
from . import choices
from .forms import OfficialJournalForm
from . exceptions import MissionCreateOrUpdateError, MissionGetError, SubjectCreationOrUpdateError


class OfficialJournal(CommonControlField):
    """
    Class that represent the Official Journal
    """

    title = models.TextField(_("Official Title"), null=True, blank=True)
    title_iso = models.TextField(_("ISO Title"), null=True, blank=True)
    foundation_year = models.CharField(
        _("Foundation Year"), max_length=4, null=True, blank=True
    )
    issn_print = models.CharField(_("ISSN Print"), max_length=9, null=True, blank=True)
    issn_electronic = models.CharField(
        _("ISSN Eletronic"), max_length=9, null=True, blank=True
    )
    issnl = models.CharField(_("ISSNL"), max_length=9, null=True, blank=True)

    base_form_class = OfficialJournalForm

    autocomplete_search_field = "title"

    def autocomplete_label(self):
        return str(self.title)

    class Meta:
        verbose_name = _("Official Journal")
        verbose_name_plural = _("Official Journals")
        indexes = [
            models.Index(
                fields=[
                    "issn_print",
                ]
            ),
            models.Index(
                fields=[
                    "issn_electronic",
                ]
            ),
            models.Index(
                fields=[
                    "issnl",
                ]
            ),
        ]

    def __unicode__(self):
        return self.title or self.issn_electronic or self.issn_print or ""

    def __str__(self):
        return self.title or self.issn_electronic or self.issn_print or ""

    @property
    def data(self):
        d = {
            "official_journal__title": self.title,
            "official_journal__foundation_year": self.foundation_year,
            "official_journal__issn_print": self.issn_print,
            "official_journal__issn_electronic": self.issn_electronic,
            "official_journal__issnl": self.issnl,
        }
        return d

    @classmethod
    def get(cls, issn_print=None, issn_electronic=None, issnl=None):
        logging.info(f"OfficialJournal.get({issn_print}, {issn_electronic}, {issnl})")
        if issn_electronic:
            return cls.objects.get(issn_electronic=issn_electronic)
        if issn_print:
            return cls.objects.get(issn_print=issn_print)
        if issnl:
            return cls.objects.get(issnl=issnl)

    @classmethod
    def create_or_update(
        cls,
        user,
        issn_print=None,
        issn_electronic=None,
        issnl=None,
        title=None,
        title_iso=None,
        foundation_year=None,
    ):
        logging.info(
            f"OfficialJournal.create_or_update({issn_print}, {issn_electronic}, {issnl})"
        )
        try:
            obj = cls.get(issn_print, issn_electronic, issnl)
            obj.updated_by = user
            obj.updated = datetime.utcnow()
        except cls.DoesNotExist:
            obj = cls()
            obj.creator = user

        obj.issnl = issnl or obj.issnl
        obj.title_iso = title_iso or obj.title_iso
        obj.title = title or obj.title
        obj.issn_print = issn_print or obj.issn_print
        obj.issn_electronic = issn_electronic or obj.issn_electronic
        obj.foundation_year = foundation_year or obj.foundation_year
        obj.save()
        logging.info(f"return {obj}")
        return obj


class Journal(CommonControlField, ClusterableModel):
    """
    Journal para site novo
    """
    short_title = models.CharField(
        _("Short Title"), max_length=100, null=True, blank=True
    )
    title = models.CharField(
        _("Title"), max_length=265, null=True, blank=True
    )
    official_journal = models.ForeignKey(
        "OfficialJournal",
        null=True,
        blank=True,
        related_name="+",
        on_delete=models.SET_NULL,
    )
    submission_online_url = models.URLField(
        _("Submission online URL"), null=True, blank=True
    )
    subject = models.ManyToManyField(
        "Subject",
        verbose_name=_("Study Areas"),
        blank=True,
    )

    def __unicode__(self):
        return self.title or self.short_title or str(self.official_journal)

    def __str__(self):
        return self.title or self.short_title or str(self.official_journal)

    base_form_class = OfficialJournalForm

    panels_identification = [
        AutocompletePanel("official_journal"),
        FieldPanel("short_title"),
    ]

    panels_owner = [
        InlinePanel("owner", label=_("Owner"), classname="collapsed"),
    ]

    panels_publisher = [
        InlinePanel("publisher", label=_("Publisher"), classname="collapsed"),
    ]

    panels_mission = [
        InlinePanel("mission", label=_("Mission"), classname="collapsed"),
    ]

    edit_handler = TabbedInterface(
        [
            ObjectList(panels_identification, heading=_("Identification")),
            ObjectList(panels_owner, heading=_("Owners")),
            ObjectList(panels_publisher, heading=_("Publisher")),
            ObjectList(panels_mission, heading=_("Mission")),
        ]
    )

    @property
    def data(self):
        return dict(
            title=self.title,
            issn_print=self.official_journal.issn_print,
            issn_electronic=self.official_journal.issn_electronic,
            foundation_year=self.official_journal.foundation_year,
            created=self.created.isoformat(),
            updated=self.updated.isoformat(),
        )

    def autocomplete_label(self):
        return self.title or self.official_journal.title

    @property
    def logo_url(self):
        return self.logo and self.logo.url

    @staticmethod
    def exists(journal_title, issn_electronic, issn_print, user):
        try:
            return Journal.get_registered(
                journal_title, issn_electronic, issn_print
            )
        except Journal.DoesNotExist:
            return Journal.fetch_and_create_journal(
                journal_title, issn_electronic, issn_print, user
            )

    @staticmethod
    def get_registered(journal_title, issn_electronic, issn_print):
        j = None
        if issn_electronic:
            try:
                j = OfficialJournal.objects.get(issn_electronic=issn_electronic)
            except OfficialJournal.DoesNotExist:
                pass

        if not j and issn_print:
            try:
                j = OfficialJournal.objects.get(issn_print=issn_print)
            except OfficialJournal.DoesNotExist:
                pass

        if not j and journal_title:
            try:
                j = OfficialJournal.objects.get(title=journal_title)
            except OfficialJournal.DoesNotExist:
                pass

        if j:
            return Journal.objects.get(official_journal=j)
        raise Journal.DoesNotExist(f"{journal_title} {issn_electronic} {issn_print}")

    @staticmethod
    def fetch_and_create_journal(
        journal_title, issn_electronic, issn_print, user,
    ):
        try:
            response = fetch_data(
                url=settings.JOURNAL_API_URL,
                params={
                    "title": journal_title,
                    "issn_print": issn_print,
                    "issn_electronic": issn_electronic,
                },
                json=True,
            )
        except Exception as e:
            logging.exception(e)
            return

        for journal in response.get("results"):
            official = journal["official"]
            official_journal = OfficialJournal.create_or_update(
                title=official["title"],
                title_iso=official["iso_short_title"],
                issn_print=official["issn_print"],
                issn_electronic=official["issn_electronic"],
                issnl=official["issnl"],
                foundation_year=official.get("foundation_year"),
                user=user,
            )
            journal = Journal.create_or_update(
                user=user,
                official_journal=official_journal,
                title=journal.get("title"),
                short_title=journal.get("short_title"),
            )
            # TODO journal collection events, dados das coleções (acron, pid, ...)
            return journal

    @classmethod
    def get(cls, official_journal):
        logging.info(f"Journal.get({official_journal})")
        if official_journal:
            return cls.objects.get(official_journal=official_journal)

    @classmethod
    def create_or_update(
        cls,
        user,
        official_journal=None,
        title=None,
        short_title=None,
    ):
        logging.info(f"Journal.create_or_update({official_journal}")
        try:
            obj = cls.get(official_journal=official_journal)
            logging.info("update {}".format(obj))
            obj.updated_by = user
            obj.updated = datetime.utcnow()
        except cls.DoesNotExist:
            obj = cls()
            obj.official_journal = official_journal
            obj.creator = user
            logging.info("create {}".format(obj))

        obj.official_journal = official_journal or obj.official_journal
        obj.title = title or obj.title
        obj.short_title = short_title or obj.short_title

        obj.save()
        logging.info(f"return {obj}")
        return obj

    @property
    def any_issn(self):
        return self.official_journal and (self.official_journal.issn_electronic or self.official_journal.issn_print)

    @property
    def max_error_percentage_accepted(self):
        values = []
        for collection in self.journal_collections:
            values.append(collection.max_error_percentage_accepted)
        # obtém o valor mais rígido se participa de mais de 1 coleção
        return min(values) or 0

    @property
    def max_absent_data_percentage_accepted(self):
        values = []
        for collection in self.journal_collections:
            values.append(collection.max_absent_data_percentage_accepted)
        # obtém o valor mais rígido se participa de mais de 1 coleção
        return min(values) or 0


class Owner(Orderable, InstitutionHistory):
    journal = ParentalKey(Journal, related_name="owner", null=True, blank=True, on_delete=models.SET_NULL)


class Publisher(Orderable, InstitutionHistory):
    journal = ParentalKey(Journal, related_name="publisher", null=True, blank=True, on_delete=models.SET_NULL)


class Sponsor(Orderable, InstitutionHistory):
    journal = ParentalKey(Journal, related_name="sponsor", null=True, blank=True, on_delete=models.SET_NULL)


class Mission(Orderable, HTMLText, CommonControlField):
    journal = ParentalKey(
        Journal, on_delete=models.SET_NULL, related_name="mission", null=True
    )

    class Meta:
        indexes = [
            models.Index(
                fields=[
                    "journal",
                ]
            ),
            models.Index(
                fields=[
                    "language",
                ]
            ),
        ]

    @property
    def data(self):
        d = {}

        if self.journal:
            d.update(self.journal.data)

        return d

    @classmethod
    def get(
        cls,
        journal,
        language,
    ):
        if journal and language:
            return cls.objects.filter(journal=journal, language=language)
        raise MissionGetError("Mission.get requires journal and language parameters")

    @classmethod
    def create_or_update(
        cls,
        user,
        journal,
        language,
        mission_text,
    ):
        if not mission_text:
            raise MissionCreateOrUpdateError(
                "Mission.create_or_update requires mission_rich_text parameter"
            )
        try:
            obj = cls.get(journal, language)
            obj.updated_by = user
        except IndexError:
            obj = cls()
            obj.creator = user
        except (MissionGetError, cls.MultipleObjectsReturned) as e:
            raise MissionCreateOrUpdateError(
                _("Unable to create or update journal {}").format(e)
            )
        obj.html_text = mission_html_text or obj.html_text
        obj.plain_text = mission_plain_text or obj.plain_text
        obj.language = language or obj.language
        obj.journal = journal or obj.journal
        obj.save()
        return obj


class JournalCollection(CommonControlField):
    journal = ParentalKey(
        Journal,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="journal_collections",
    )
    collection = models.ForeignKey(
        Collection,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    pid = models.CharField(_("Journal PID"), null=True, blank=True, max_length=9)
    journal_acron = models.CharField(_("Journal acron"), null=True, blank=True, max_length=16)
    website_publication_date = models.DateTimeField(
        blank=True,
        null=True,
    )


class JournalCollectionEvent(CommonControlField):
    journal_collection = ParentalKey(
        JournalCollection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="journal_events",
    )

    year = models.CharField(_("Event year"), max_length=4, null=True, blank=True)
    month = models.CharField(
        _("Event month"),
        max_length=2,
        choices=MONTHS,
        null=True,
        blank=True,
    )
    day = models.CharField(_("Event day"), max_length=2, null=True, blank=True)

    event_type = models.CharField(
        _("Event type"),
        null=True,
        blank=True,
        max_length=16,
        choices=choices.JOURNAL_EVENT_TYPE,
    )
    interruption_reason = models.CharField(
        _("Indexing interruption reason"),
        null=True,
        blank=True,
        max_length=24,
        choices=choices.INDEXING_INTERRUPTION_REASON,
    )

    base_form_class = CoreAdminModelForm

    panels = [
        FieldPanel("year"),
        FieldPanel("month"),
        FieldPanel("day"),
        FieldPanel("event_type"),
        FieldPanel("interruption_reason"),
    ]

    class Meta:
        verbose_name = _("Event")
        verbose_name_plural = _("Events")
        unique_together = ("journal_collection", "event_type", "year", "month", "day")
        ordering = ("journal_collection", "-year", "-month", "-day")
        indexes = [
            models.Index(
                fields=[
                    "event_type",
                ]
            ),
        ]

    @classmethod
    def get(cls, journal_collection, event_type, year, month, day, interruption_reason=None):
        return cls.objects.get(
            journal_collection=journal_collection,
            event_type=event_type,
            year=year,
            month=month,
            day=day,
        )

    @classmethod
    def create(cls, user, journal_collection, event_type, year, month, day, interruption_reason=None):
        try:
            obj = cls()
            obj.journal_collection = journal_collection
            obj.event_type = event_type
            obj.year = year
            obj.month = month
            obj.day = day
            obj.interruption_reason = interruption_reason
            obj.creator = user
            obj.save()
            return obj
        except IntegrityError:
            return cls.get(journal_collection, event_type, year, month, day)

    @classmethod
    def create_or_update(cls, user, journal_collection, event_type, year, month, day, interruption_reason=None):
        try:
            obj = cls.get(journal_collection, event_type, year, month, day)
            obj.interruption_reason = interruption_reason
            obj.creator = obj.creator or user
            obj.updated_by = obj.updated_by or user
            obj.save()
        except cls.DoesNotExist:
            return cls.create(
                user, journal_collection, event_type, year, month, day, interruption_reason
            )

    @property
    def data(self):
        d = {
            "event_type": self.event_type,
            "interruption_reason": self.interruption_reason,
            "year": self.year,
            "month": self.month,
            "day": self.day,
        }

        return d

    @property
    def date(self):
        return f"{self.year}-{str(self.month).zfill(2)}-{str(self.day).zfill(2)}"

    @property
    def opac_event_type(self):
        if self.event_type == "ADMITTED":
            return "current"
        if 'suspended' in self.interruption_reason:
            return 'suspended'
        return 'inprogress'

    def __str__(self):
        return f"{self.event_type} {self.interruption_reason} {self.year}/{self.month}/{self.day}"


class Subject(CommonControlField):
    code = models.CharField(max_length=30, null=True, blank=True)
    value = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        return f"{self.value}"

    @classmethod
    def load(cls, user):
        if not cls.objects.exists():
            for item in choices.STUDY_AREA:
                code, _ = item
                cls.create_or_update(
                    code=code,
                    user=user,
                )

    @classmethod
    def get(cls, code):
        if not code:
            raise ValueError("Subject.get requires code parameter")
        return cls.objects.get(code=code)

    @classmethod
    def create_or_update(
        cls,
        code,
        user,
    ):
        try:
            obj = cls.get(code=code)
        except cls.DoesNotExist:
            obj = cls()
            obj.code = code
            obj.creator = user
        except SubjectCreationOrUpdateError as e:
            raise SubjectCreationOrUpdateError(code=code, message=e)

        obj.value = dict(choices.STUDY_AREA).get(code) or obj.value
        obj.updated = user
        obj.save()
        return obj
