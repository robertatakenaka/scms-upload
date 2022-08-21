from django.db import models
from django.utils.translation import gettext_lazy as _

from wagtail.admin.edit_handlers import FieldPanel, MultiFieldPanel

from core.models import CommonControlField

from . import choices


class PDFIssueFiles:
    def __init__(self):
        self.pdfs = None

    def add_item(self, key, lang, name, uri):
        if not self.pdfs:
            self.pdfs.setdefault(key, {})
        self.pdfs[key][lang] = {
            "name": name,
            "uri": uri,
        }

    def get_item(self, key, lang):
        return self.pdfs[key][lang]


class PDFIssueFiles:
    def __init__(self, items=None):
        self.items = items

    def add_item(self, key, lang, name, uri):
        if not self.items:
            self.items = {}
            self.items.setdefault(key, {})
        self.items[key][lang] = {
            "name": name,
            "uri": uri,
        }

    def get_item(self, key, lang):
        return self.items[key][lang]


class XMLIssueFiles:
    def __init__(self, items=None):
        self.items = items

    def add_item(self, key, name, uri):
        if not self.items:
            self.items = {}
            self.items.setdefault(key, {})
        self.items[key] = {
            "name": name,
            "uri": uri,
        }

    def get_item(self, key):
        return self.items[key]


class AssetIssueFiles:
    def __init__(self, items=None):
        self.items = items

    def add_item(self, name, uri):
        if not self.items:
            self.items = {}
            self.items.setdefault(key, {})
        self.items[name] = uri

    def get_item(self, name):
        return self.items[name]


class HTMLIssueFiles:
    def __init__(self, items=None):
        self.items = items

    def add_item(self, key, lang, name, uri, part):
        if not self.items:
            self.items = {}
            self.items.setdefault(key, {})
        self.items[key][lang].setdefault(part, {})
        self.items[key][lang][part] = {
            "name": name,
            "uri": uri,
        }

    def get_item(self, key, lang):
        return self.items[key][lang][part]


class JournalMigration(CommonControlField):

    scielo_issn = models.CharField(
        _('SciELO ISSN'), max_length=9, null=False, blank=False)
    acron = models.CharField(
        _('Acronym'), max_length=20, null=False, blank=False)
    title = models.CharField(
        _('Title'), max_length=200, null=False, blank=False)

    # datas no registro da base isis para identificar
    # se houve mudança durante a migração
    isis_updated_date = models.CharField(
        _('ISIS updated date'), max_length=8, null=False, blank=False)
    isis_created_date = models.CharField(
        _('ISIS created date'), max_length=8, null=False, blank=False)

    # status do registro quanto aos metadados
    status = models.CharField(
        _('Status'), max_length=20,
        choices=choices.MIGRATION_STATUS,
        default=choices.MS_TO_MIGRATE,
    )

    record = models.JSONField(blank=False)

    def __str__(self):
        return f"{self.acron} {self.scielo_issn} {self.status}"


class IssueMigration(CommonControlField):

    scielo_issn = models.CharField(
        _('SciELO ISSN'), max_length=9, null=False, blank=False)
    acron = models.CharField(
        _('Acronym'), max_length=20, null=False, blank=False)
    issue_pid = models.CharField(
        _('Issue PID'), max_length=17, null=False, blank=False)
    year = models.CharField(
        _('Publication Year'), max_length=4, null=False, blank=False
    )

    # datas no registro da base isis para identificar
    # se houve mudança durante a migração
    isis_updated_date = models.CharField(
        _('ISIS updated date'), max_length=8, null=False, blank=False)
    isis_created_date = models.CharField(
        _('ISIS created date'), max_length=8, null=False, blank=False)

    # status do registro quanto aos metadados
    status = models.CharField(
        _('Status'), max_length=20,
        choices=choices.MIGRATION_STATUS,
        default=choices.MS_TO_MIGRATE,
    )

    record = models.JSONField(blank=False)

    def __str__(self):
        return f"{self.acron} {self.issue_pid} {self.status}"


class IssueFilesMigration(CommonControlField):

    acron = models.CharField(
        _('Acronym'), max_length=20, null=False, blank=False)
    issue_folder = models.CharField(
        _('IssueFiles PID'), max_length=20, null=False, blank=False)
    issue_pid = models.CharField(
        _('Issue PID'), max_length=17, null=False, blank=False)

    # status do registro quanto aos metadados
    status = models.CharField(
        _('Status'), max_length=20,
        choices=choices.MIGRATION_STATUS,
        default=choices.MS_TO_MIGRATE,
    )

    xmls = models.JSONField(blank=False)
    htmls = models.JSONField(blank=False)
    pdfs = models.JSONField(blank=False)
    assets = models.JSONField(blank=False)

    def __str__(self):
        return f"{self.acron} {self.issue_folder} {self.status}"


class DocumentMigration(CommonControlField):

    scielo_issn = models.CharField(
        _('SciELO ISSN'), max_length=9, null=False, blank=False)
    acron = models.CharField(
        _('Acronym'), max_length=20, null=False, blank=False)
    pid = models.CharField(
        _('Document PID'), max_length=9, null=False, blank=False)
    year = models.CharField(
        _('Publication Year'), max_length=4, null=False, blank=False
    )

    # datas no registro da base isis para identificar
    # se houve mudança durante a migração
    isis_updated_date = models.CharField(
        _('ISIS updated date'), max_length=8, null=False, blank=False)
    isis_created_date = models.CharField(
        _('ISIS created date'), max_length=8, null=False, blank=False)

    # status do registro quanto aos metadados
    status = models.CharField(
        _('Status'), max_length=20,
        choices=choices.MIGRATION_STATUS,
        default=choices.MS_TO_MIGRATE,
    )

    records = models.JSONField(blank=False)

    def __str__(self):
        return f"{self.acron} {self.pid} {self.status}"


class DocumentFilesMigration(CommonControlField):

    pid = models.CharField(
        _('Document PID'), max_length=9, null=False, blank=False)
    acron = models.CharField(
        _('Acronym'), max_length=20, null=False, blank=False)
    issue_folder = models.CharField(
        _('Issue folder'), max_length=20, null=False, blank=False)
    filename_without_extension = models.CharField(
        _('File name'), max_length=20, null=False, blank=False)

    # status do registro quanto aos metadados
    status = models.CharField(
        _('Status'), max_length=20,
        choices=choices.MIGRATION_STATUS,
        default=choices.MS_TO_MIGRATE,
    )

    htmls = models.JSONField(blank=False)
    xmls = models.JSONField(blank=False)
    pdfs = models.JSONField(blank=False)
    assets = models.JSONField(blank=False)

    def __str__(self):
        return f"{self.acron} {self.pid} {self.status}"
