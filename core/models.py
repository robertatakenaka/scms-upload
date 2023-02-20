from django.db import models
from django.contrib.auth import get_user_model
from django.utils.translation import gettext as _
from wagtail.core.fields import RichTextField
from wagtail.admin.edit_handlers import FieldPanel
from . import choices


User = get_user_model()


def get_sentinel_user():
    return get_user_model().objects.get_or_create(username='deleted')[0]


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
    created = models.DateTimeField(
        verbose_name=_("Creation date"), auto_now_add=True
    )

    # Update date
    updated = models.DateTimeField(
        verbose_name=_("Last update date"), auto_now=True
    )

    # Creator user
    creator = models.ForeignKey(
        User,
        verbose_name=_("Creator"),
        related_name="%(class)s_creator",
        editable=False,
        on_delete=models.SET(get_sentinel_user),
    )

    # Last modifier user
    updated_by = models.ForeignKey(
        User,
        verbose_name=_("Updater"),
        related_name="%(class)s_last_mod_user",
        editable=False,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    class Meta:
        abstract = True


class Language(CommonControlField):
    """
    Represent the list of states

    Fields:
        name
        code2
    """
    name = models.CharField(_("Language Name"), blank=True, null=True, max_length=255)
    code2 = models.CharField(_("Language code 2"), blank=True, null=True, max_length=2)

    class Meta:
        verbose_name = _("Language")
        verbose_name_plural = _("Languages")

    def __unicode__(self):
        return self.code2 or 'idioma ausente / não informado'

    def __str__(self):
        return self.code2 or 'idioma ausente / não informado'

    @classmethod
    def get_or_create(cls, name=None, code2=None, creator=None):

        if code2:
            try:
                return cls.objects.get(code2__icontains=code2)
            except:
                pass

        if name:
            try:
                return cls.objects.get(name__icontains=name)
            except:
                pass

        if name or code2:
            obj = Language()
            obj.name = name
            obj.code2 = code2 or ''
            obj.creator = creator or ''
            obj.save()
            return obj


class RichTextWithLang(models.Model):
    text = RichTextField(null=False, blank=False)
    language = models.CharField(_('Language'), max_length=2, choices=choices.LANGUAGE, null=False, blank=False)

    panels = [
        FieldPanel('text'),
        FieldPanel('language')
    ]

    class Meta:
        abstract = True


class TextWithLangAndValidity(models.Model):
    text = models.CharField(_('Text'), max_length=255, null=False, blank=False)
    language = models.CharField(_('Language'), max_length=2, choices=choices.LANGUAGE, null=False, blank=False)
    initial_date = models.DateField(null=True, blank=True)
    final_date = models.DateField(null=True, blank=True)

    panels = [
        FieldPanel('text'),
        FieldPanel('language'),
        FieldPanel('initial_date'),
        FieldPanel('final_date')
    ]

    class Meta:
        abstract = True


class RichTextWithLangAndValidity(RichTextWithLang):
    initial_date = models.DateField(null=True, blank=True)
    final_date = models.DateField(null=True, blank=True)

    panels = [
        FieldPanel('text'),
        FieldPanel('language'),
        FieldPanel('initial_date'),
        FieldPanel('final_date')
    ]

    class Meta:
        abstract = True


class TextWithLang(models.Model):
    text = models.CharField(_('Text'), max_length=255, null=False, blank=False)
    language = models.CharField(_('Language'), max_length=2, choices=choices.LANGUAGE, null=False, blank=False)

    panels = [
        FieldPanel('text'),
        FieldPanel('language')
    ]

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
        return {
            k: v
            for k, v in date.items()
            if v
        }

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
        return {
            k: v
            for k, v in date.items()
            if v
        }

    class Meta:
        abstract = True


class FlexibleDateFieldAdapter:

    def __init__(self,
                 text=None,
                 year=None,
                 first_month_number=None, first_month_name=None,
                 last_month_number=None, last_month_name=None,
                 day=None,
                 data=None):
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
