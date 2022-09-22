from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import CommonControlField

from collection.models import (
    SciELOJournal,
    SciELOIssue,
    SciELODocument,
    NewWebSiteConfiguration,
    FilesStorageConfiguration,
    ClassicWebsiteConfiguration,
)

from . import choices


class MigrationConfiguration(CommonControlField):

    classic_website_config = models.ForeignKey(
        ClassicWebsiteConfiguration, on_delete=models.CASCADE)
    new_website_config = models.ForeignKey(
        NewWebSiteConfiguration, on_delete=models.CASCADE)
    files_storage_config = models.ForeignKey(
        FilesStorageConfiguration, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.classic_website_config}"

    class Meta:
        indexes = [
            models.Index(fields=['classic_website_config']),
        ]


class MigratedData(CommonControlField):

    # datas no registro da base isis para identificar
    # se houve mudança nos dados durante a migração
    isis_updated_date = models.CharField(
        _('ISIS updated date'), max_length=8, null=True, blank=True)
    isis_created_date = models.CharField(
        _('ISIS created date'), max_length=8, null=True, blank=True)

    # dados migrados
    data = models.JSONField(blank=True, null=True)

    # status da migração
    status = models.CharField(
        _('Status'), max_length=20,
        choices=choices.MIGRATION_STATUS,
        default=choices.MS_TO_MIGRATE,
    )

    class Meta:
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['isis_updated_date']),
        ]


class MigrationFailure(CommonControlField):
    action_name = models.CharField(
        _('Action'), max_length=255, null=False, blank=False)
    object_name = models.CharField(
        _('Object'), max_length=255, null=False, blank=False)
    pid = models.CharField(
        _('Item PID'), max_length=23, null=False, blank=False)
    exception_type = models.CharField(
        _('Exception Type'), max_length=255, null=False, blank=False)
    exception_msg = models.CharField(
        _('Exception Msg'), max_length=555, null=False, blank=False)
    traceback = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['object_name']),
            models.Index(fields=['pid']),
            models.Index(fields=['action_name']),
        ]


class JournalMigration(MigratedData):

    scielo_journal = models.ForeignKey(SciELOJournal, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.scielo_journal} {self.status}"

    class Meta:
        indexes = [
            models.Index(fields=['scielo_journal']),
        ]


class IssueMigration(MigratedData):

    scielo_issue = models.ForeignKey(SciELOIssue, on_delete=models.CASCADE)

    def __unicode__(self):
        return f"{self.scielo_issue} {self.status}"

    def __str__(self):
        return f"{self.scielo_issue} {self.status}"

    class Meta:
        indexes = [
            models.Index(fields=['scielo_issue']),
        ]


class DocumentMigration(MigratedData):

    scielo_document = models.ForeignKey(SciELODocument, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.scielo_document} {self.status}"

    class Meta:
        indexes = [
            models.Index(fields=['scielo_document']),
        ]

#########################################################################


class SciELOFile(CommonControlField):

    file_id = models.CharField(_('ID'), max_length=255, null=False, blank=False)
    name = models.CharField(_('Filename'), max_length=255, null=False, blank=False)
    uri = models.CharField(_('URI'), max_length=255, null=True)
    object_name = models.CharField(_('Object name'), max_length=255, null=True)

    def __str__(self):
        return f"{self.name}"

    class Meta:

        indexes = [
            models.Index(fields=['file_id']),
            models.Index(fields=['name']),
            models.Index(fields=['object_name']),
        ]


class SciELOFileWithLang(SciELOFile):

    lang = models.CharField(
        _('Language'), max_length=2, null=False, blank=False)

    class Meta:

        indexes = [
            models.Index(fields=['lang']),
        ]


class SciELOHTMLFile(SciELOFileWithLang):

    part = models.CharField(
        _('Part'), max_length=5, null=False, blank=False)

    class Meta:

        indexes = [
            models.Index(fields=['part']),
        ]


class BaseFilesMigration(CommonControlField):

    htmls = models.ManyToManyField(SciELOHTMLFile, blank=True, related_name='htmls')
    xmls = models.ManyToManyField(SciELOFile, blank=True, related_name='xmls')
    pdfs = models.ManyToManyField(SciELOFileWithLang, blank=True, related_name='pdfs')
    assets = models.ManyToManyField(SciELOFile, blank=True, related_name='assets')

    status = models.CharField(
        _('Status'), max_length=20,
        choices=choices.MIGRATION_STATUS,
        default=choices.MS_TO_MIGRATE,
    )


class IssueFilesMigration(BaseFilesMigration):

    scielo_issue = models.ForeignKey(SciELOIssue, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.scielo_issue} {self.status}"

    class Meta:

        indexes = [
            models.Index(fields=['scielo_issue']),
        ]


class DocumentFilesMigration(BaseFilesMigration):

    scielo_document = models.ForeignKey(SciELODocument, on_delete=models.CASCADE)
    suppl_mats = models.ManyToManyField(SciELOFile, blank=True, related_name='suppl_mats')

    def __str__(self):
        return f"{self.scielo_document} {self.status}"

    class Meta:

        indexes = [
            models.Index(fields=['scielo_document']),
        ]
