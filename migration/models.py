from django.db import models
from django.utils.translation import gettext_lazy as _

from wagtail.admin.edit_handlers import FieldPanel, MultiFieldPanel

from core.models import CommonControlField

from . import choices


class JournalMigrationTracker(CommonControlField):

    scielo_issn = models.CharField(
        _('SciELO ISSN'), max_length=9, null=False, blank=False)
    acron = models.CharField(
        _('Acronym'), max_length=20, null=False, blank=False)

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

    journal = models.ForeignKey('MigratedJournal')

    def __str__(self):
        return f"{self.acron} {self.scielo_issn} {self.status}"


class MigratedJournal(CommonControlField):

    scielo_issn = models.CharField(
        _('SciELO ISSN'), max_length=9, null=False, blank=False)
    acron = models.CharField(
        _('Acronym'), max_length=20, null=False, blank=False)
    title = models.CharField(
        _('Title'), max_length=200, null=False, blank=False)

    # registro no formato json correspondente ao conteúdo da base isis
    record = models.JSONField(blank=False)

    def __str__(self):
        return f"{self.acron} {self.scielo_issn} {self.title}"


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

    info = models.JSONField(blank=False)
    paths = models.JSONField(blank=False)

    def __str__(self):
        return f"{self.acron} {self.issue_folder} {self.status}"


class DocumentMigrationTracker(CommonControlField):

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

    migrated_doc = models.ForeignKey('MigratedDocument')

    def __str__(self):
        return f"{self.acron} {self.pid} {self.status}"


class MigratedDocument(CommonControlField):

    pid = models.CharField(
        _('Document PID'), max_length=23, null=False, blank=False)
    # registro no formato json correspondente ao conteúdo da base isis
    record = models.JSONField(blank=False)

    def __str__(self):
        return f"{self.pid}"
