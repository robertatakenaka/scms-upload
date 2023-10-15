import json
import logging
import os
import traceback
from datetime import datetime
import uuid

from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext as _
from wagtail.admin.panels import FieldPanel
from wagtail.fields import RichTextField
from wagtail.snippets.models import register_snippet

from core.forms import CoreAdminModelForm

from . import choices

User = get_user_model()


class CommonControlField(models.Model):
    """
    Class with common control fields.

    Fields:
        created: Date time when the record was created
        updated: Date time with the last update date
        creator: The creator of the record
        updated_by: Store the last updator of the record
    """

    # Creation date
    created = models.DateTimeField(verbose_name=_("Creation date"), auto_now_add=True)

    # Update date
    updated = models.DateTimeField(verbose_name=_("Last update date"), auto_now=True)

    # Creator user
    creator = models.ForeignKey(
        User,
        verbose_name=_("Creator"),
        related_name="%(class)s_creator",
        editable=False,
        on_delete=models.CASCADE,
    )

    # Last modifier user
    updated_by = models.ForeignKey(
        User,
        verbose_name=_("Updater"),
        related_name="%(class)s_last_mod_user",
        editable=False,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
    )

    @classmethod
    def get_latest_change(cls):
        dates = []
        try:
            dates.append(cls.objects.latest("updated").updated)
        except:
            pass
        try:
            dates.append(cls.objects.latest("created").created)
        except:
            pass
        try:
            return max(dates)
        except ValueError:
            return

    class Meta:
        abstract = True

    base_form_class = CoreAdminModelForm


class Incident(CommonControlField):
    report = models.ForeignKey(
        "IncidentReport", on_delete=models.SET_NULL, null=True, blank=True
    )
    message = models.TextField(_("Message"), null=True, blank=True)
    context = models.CharField(_("Context"), max_length=64, null=True, blank=True)
    item_name = models.CharField(_("Item name"), max_length=64, null=True, blank=True)
    item_id = models.CharField(_("Item id"), max_length=64, null=True, blank=True)
    exception_type = models.TextField(_("Exception Type"), null=True, blank=True)
    exception_msg = models.TextField(_("Exception Msg"), null=True, blank=True)
    traceback = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["exception_type"]),
        ]

    @property
    def data(self):
        return dict(
            context=self.context,
            exception_msg=self.exception_msg,
            exception_type=self.exception_type,
            item_id=self.item_id,
            item_name=self.item_name,
            message=self.message,
            traceback=self.traceback,
        )

    @classmethod
    def create(
        cls,
        report,
        user=None,
        context=None,
        item_name=None,
        item_id=None,
        e=None,
        message=None,
        exc_traceback=None,
    ):
        if message:
            logging.info(message)
        if e:
            logging.exception(e)

        obj = cls()
        obj.report = report
        obj.context = context
        obj.item_name = item_name
        obj.item_id = item_id
        obj.message = message
        obj.exception_msg = e and str(e)
        obj.exception_type = e and str(type(e))
        obj.creator = user
        if exc_traceback:
            obj.traceback = [str(item) for item in traceback.extract_tb(exc_traceback)]
        obj.save()
        return obj


class IncidentReport(CommonControlField):
    report_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    collection_acron = models.CharField(
        _("Collection acron"), max_length=64, null=True, blank=True
    )
    app_name = models.CharField(_("App name"), max_length=64, null=True, blank=True)
    status = models.CharField(_("Status"), max_length=64, null=True, blank=True)
    incidents = models.ManyToManyField(Incident)

    class Meta:
        indexes = [
            models.Index(fields=["collection_acron"]),
            models.Index(fields=["app_name"]),
            models.Index(fields=["status"]),
        ]

    @property
    def items(self):
        return [item.data for item in self.incidents.all()]

    @classmethod
    def get(cls, report_id):
        return cls.objects.get(report_id=report_id)

    @classmethod
    def get_or_create(cls, user, collection_acron, app_name):
        try:
            return cls.objects.get(
                collection_acron=collection_acron,
                app_name=app_name,
                status__isnull=True,
            )
        except cls.DoesNotExist:
            return cls.create(
                collection_acron=collection_acron,
                app_name=app_name,
                user=user,
            )
        except cls.MultipleObjectsReturned:
            return cls.objects.filter(
                collection_acron=collection_acron,
                app_name=app_name,
                status__isnull=True,
            ).latest("created")

    @classmethod
    def create(
        cls,
        collection_acron=None,
        app_name=None,
        user=None,
    ):
        obj = cls()
        obj.creator = user
        obj.collection_acron = collection_acron
        obj.app_name = app_name
        obj.save()
        return obj

    def add_incident(
        self,
        user=None,
        context=None,
        item_name=None,
        item_id=None,
        e=None,
        message=None,
        exc_traceback=None,
    ):
        obj = Incident.create(
            report=self,
            user=user,
            context=context,
            item_name=item_name,
            item_id=item_id,
            e=e,
            message=message,
            exc_traceback=exc_traceback,
        )
        self.incidents.add(obj)
        return obj


class IncidentTracker(models.Model):
    incident_report = models.ForeignKey(
        IncidentReport, on_delete=models.SET_NULL, null=True, blank=True
    )

    @property
    def incidents_number(self):
        if self.incident_report:
            return self.incident_report.incidents.count()
        return 0

    @property
    def incident_report_data(self):
        return self.incident_report.items

    @classmethod
    def register_incident(
        self,
        collection_acron=None,
        app_name=None,
        user=None,
        context=None,
        item_name=None,
        item_id=None,
        e=None,
        message=None,
        exc_traceback=None,
    ):
        incident_report = IncidentReport.get_or_create(
            user=user,
            collection_acron=collection_acron,
            app_name=app_name,
        )
        incident_tracker, created = IncidentTracker.objects.get_or_create(
            user=user, incident_report=incident_report
        )
        return incident_report.add_incident(
            user=user,
            context=context,
            item_name=item_name,
            item_id=item_id,
            e=e,
            message=message,
            exc_traceback=exc_traceback,
        )

    def archive_incident_report(self):
        if self.incident_report:
            self.incident_report.status = "archived"
            self.incident_report.save()

            self.incident_report = None
            self.save()

    def add_incident(
        self,
        collection_acron=None,
        app_name=None,
        user=None,
        context=None,
        item_name=None,
        item_id=None,
        e=None,
        message=None,
        exc_traceback=None,
    ):
        if not self.incident_report:
            self.incident_report = IncidentReport.get_or_create(
                user=user,
                collection_acron=collection_acron,
                app_name=app_name,
            )
        return self.incident_report.add_incident(
            user=user,
            context=context,
            item_name=item_name,
            item_id=item_id,
            e=e,
            message=message,
            exc_traceback=exc_traceback,
        )


class GlobalIncidentTracker(IncidentTracker):
    ...


class RichTextWithLang(models.Model):
    text = RichTextField(null=False, blank=False)
    language = models.CharField(
        _("Language"), max_length=2, choices=choices.LANGUAGE, null=False, blank=False
    )

    panels = [FieldPanel("text"), FieldPanel("language")]

    class Meta:
        abstract = True


class TextWithLangAndValidity(models.Model):
    text = models.TextField(_("Text"), null=False, blank=False)
    language = models.CharField(
        _("Language"), max_length=2, choices=choices.LANGUAGE, null=False, blank=False
    )
    initial_date = models.DateField(null=True, blank=True)
    final_date = models.DateField(null=True, blank=True)

    panels = [
        FieldPanel("text"),
        FieldPanel("language"),
        FieldPanel("initial_date"),
        FieldPanel("final_date"),
    ]

    class Meta:
        abstract = True


class RichTextWithLangAndValidity(RichTextWithLang):
    initial_date = models.DateField(null=True, blank=True)
    final_date = models.DateField(null=True, blank=True)

    panels = [
        FieldPanel("text"),
        FieldPanel("language"),
        FieldPanel("initial_date"),
        FieldPanel("final_date"),
    ]

    class Meta:
        abstract = True


class TextWithLang(models.Model):
    text = models.TextField(_("Text"), null=False, blank=False)
    language = models.CharField(
        _("Language"), max_length=2, choices=choices.LANGUAGE, null=False, blank=False
    )

    panels = [FieldPanel("text"), FieldPanel("language")]

    class Meta:
        abstract = True


class PublicationMonthModel(models.Model):
    """
    Class PublicationMonthModel

    """

    publication_month_number = models.IntegerField(
        verbose_name=_("Publication month number"),
        null=True,
        blank=True,
        choices=choices.MONTHS,
    )
    publication_month_name = models.CharField(
        verbose_name=_("Publication month name"),
        max_length=20,
        null=True,
        blank=True,
    )

    class Meta:
        abstract = True


class PublicationMonthsRangeModel(models.Model):
    """
    Class PublicationMonthsRangeModel

    """

    publication_initial_month_number = models.IntegerField(
        verbose_name=_("Publication initial month number"),
        choices=choices.MONTHS,
        null=True,
        blank=True,
    )
    publication_initial_month_name = models.CharField(
        verbose_name=_("Publication initial month name"),
        max_length=20,
        null=True,
        blank=True,
    )
    publication_final_month_number = models.IntegerField(
        verbose_name=_("Publication final month number"),
        choices=choices.MONTHS,
        null=True,
        blank=True,
    )
    publication_final_month_name = models.CharField(
        verbose_name=_("Publication final month name"),
        max_length=20,
        null=True,
        blank=True,
    )

    class Meta:
        abstract = True


class IssuePublicationDate(PublicationMonthsRangeModel):
    """
    Class IssuePublicationDate
    """

    publication_date_text = models.CharField(
        verbose_name=_("Publication date text"),
        max_length=255,
        null=True,
    )
    publication_year = models.IntegerField(
        verbose_name=_("Publication year"),
        null=True,
    )

    @property
    def publication_date(self):
        date = {
            "publication_date_text": self.publication_date_text,
            "publication_year": self.publication_year,
            "publication_initial_month_name": self.publication_initial_month_name,
            "publication_initial_month_number": self.publication_initial_month_number,
            "publication_final_month_name": self.publication_final_month_name,
            "publication_final_month_number": self.publication_final_month_number,
        }
        return {k: v for k, v in date.items() if v}

    class Meta:
        abstract = True


class DocumentPublicationDate(IssuePublicationDate):
    """
    Class IssuePublicationDate
    """

    publication_day = models.IntegerField(
        verbose_name=_("Publication year"),
        null=True,
    )

    @property
    def publication_date(self):
        date = {
            "publication_date_text": self.publication_date_text,
            "publication_year": self.publication_year,
            "publication_initial_month_name": self.publication_initial_month_name,
            "publication_initial_month_number": self.publication_initial_month_number,
            "publication_final_month_name": self.publication_final_month_name,
            "publication_final_month_number": self.publication_final_month_number,
            "publication_day": self.publication_day,
        }
        return {k: v for k, v in date.items() if v}

    class Meta:
        abstract = True


class FlexibleDateFieldAdapter:
    def __init__(
        self,
        text=None,
        year=None,
        first_month_number=None,
        first_month_name=None,
        last_month_number=None,
        last_month_name=None,
        day=None,
        data=None,
    ):
        self._data = data or {}
        self._text = data.get("text") or text
        self._year = data.get("year") or year
        self._first_month_number = data.get("first_month_number") or first_month_number
        self._last_month_number = data.get("last_month_number") or last_month_number
        self._first_month_name = data.get("first_month_name") or first_month_name
        self._last_month_name = data.get("last_month_name") or last_month_name
        self._day = data.get("day") or day

    @property
    def data(self):
        if not self._data:
            names = (
                "text",
                "year",
                "first_month_name",
                "first_month_number",
                "last_month_name",
                "last_month_number",
                "day",
            )
            values = (
                self.text,
                self.year,
                self.first_month_name,
                self.first_month_number,
                self.last_month_name,
                self.last_month_number,
                self.day,
            )
            self._data = {}
            for name, value in zip(names, values):
                if value:
                    self._data[name] = value
        return self._data

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, value):
        # TODO parse value e preenche day, month, year
        self._text = value

    @property
    def day(self):
        return self._day

    @day.setter
    def day(self, value):
        self._day = int(value)

    @property
    def last_month_name(self):
        return self._last_month_name

    @last_month_name.setter
    def last_month_name(self, value):
        self._last_month_name = value

    @property
    def first_month_name(self):
        return self._first_month_name

    @first_month_name.setter
    def first_month_name(self, value):
        self._first_month_name = value

    @property
    def last_month_number(self):
        return self._last_month_number

    @last_month_number.setter
    def last_month_number(self, value):
        self._last_month_number = int(value)

    @property
    def first_month_number(self):
        return self._first_month_number

    @first_month_number.setter
    def first_month_number(self, value):
        self._first_month_number = int(value)

    @property
    def year(self):
        return self._year

    @year.setter
    def year(self, value):
        self._year = int(value)
