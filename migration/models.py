import logging

from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import CommonControlField
from core.forms import CoreAdminModelForm
from collection.models import (
    SciELOJournal,
    SciELOIssue,
    SciELODocument,
    NewWebSiteConfiguration,
    ClassicWebsiteConfiguration,
)
from files_storage.models import Configuration as FilesStorageConfiguration
from . import choices
from . import exceptions
from .choices import MS_IMPORTED, MS_PUBLISHED, MS_TO_IGNORE


class MigrationConfiguration(CommonControlField):

    classic_website_config = models.ForeignKey(
        ClassicWebsiteConfiguration,
        verbose_name=_('Classic website configuration'),
        null=True, blank=True,
        on_delete=models.SET_NULL)
    new_website_config = models.ForeignKey(
        NewWebSiteConfiguration,
        verbose_name=_('New website configuration'),
        null=True, blank=True,
        on_delete=models.SET_NULL)
    public_files_storage_config = models.ForeignKey(
        FilesStorageConfiguration,
        verbose_name=_('Public Files Storage Configuration'),
        related_name='public_files_storage_config',
        null=True, blank=True,
        on_delete=models.SET_NULL)
    migration_files_storage_config = models.ForeignKey(
        FilesStorageConfiguration,
        verbose_name=_('Migration Files Storage Configuration'),
        related_name='migration_files_storage_config',
        null=True, blank=True,
        on_delete=models.SET_NULL)

    def __str__(self):
        return f"{self.classic_website_config}"

    @classmethod
    def get_or_create(cls, classic_website, new_website_config=None,
                      public_files_storage_config=None,
                      migration_files_storage_config=None,
                      creator=None,
                      ):
        logging.info(_("Get or create migration configuration"))
        try:
            return cls.objects.get(classic_website_config=classic_website)
        except cls.DoesNotExist:
            migration_configuration = cls()
            migration_configuration.classic_website_config = classic_website
            migration_configuration.new_website_config = new_website_config
            migration_configuration.public_files_storage_config = public_files_storage_config
            migration_configuration.migration_files_storage_config = migration_files_storage_config
            migration_configuration.creator = creator
            migration_configuration.save()
            return migration_configuration

    class Meta:
        indexes = [
            models.Index(fields=['classic_website_config']),
        ]
    base_form_class = CoreAdminModelForm


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

    @classmethod
    def get_or_create(cls, scielo_journal, creator):
        """
        Returns a JournalMigration (registered or new)
        """
        try:
            return cls.objects.get(
                scielo_journal=scielo_journal,
            )
        except cls.DoesNotExist:
            item = cls()
            item.creator = creator
            item.scielo_journal = scielo_journal
            item.save()
            return item
        except Exception as e:
            raise exceptions.GetOrCreateJournalMigrationError(
                _('Unable to get_or_create_journal_migration {} {} {}').format(
                    scielo_journal, type(e), e
                )
            )

    def update(self, journal, journal_data, force_update):
        # check if it needs to be update
        if self.isis_updated_date == journal.isis_updated_date:
            if not force_update:
                # nao precisa atualizar
                return

        self.isis_created_date = journal.isis_created_date
        self.isis_updated_date = journal.isis_updated_date
        self.status = MS_IMPORTED
        if journal.current_status != CURRENT:
            self.status = MS_TO_IGNORE
        self.data = journal_data
        self.save()

    class Meta:
        indexes = [
            models.Index(fields=['scielo_journal']),
            models.Index(fields=['status']),
            models.Index(fields=['isis_updated_date']),
        ]


class IssueMigration(MigratedData):

    scielo_issue = models.ForeignKey(SciELOIssue, on_delete=models.CASCADE)
    files_status = models.CharField(
        _('Status'), max_length=20,
        choices=choices.MIGRATION_STATUS,
        default=choices.MS_TO_MIGRATE,
    )

    def __str__(self):
        return f"{self.scielo_issue} | data: {self.status} | files: {self.files_status}"

    @classmethod
    def get_or_create(cls, scielo_issue, creator):
        """
        Returns a IssueMigration (registered or new)
        """
        try:
            return cls.objects.get(
                scielo_issue=scielo_issue,
            )
        except cls.DoesNotExist:
            item = cls()
            item.creator = creator
            item.scielo_issue = scielo_issue
            item.save()
            return item
        except Exception as e:
            raise exceptions.GetOrCreateIssueMigrationError(
                _('Unable to get_or_create_issue_migration {} {} {}').format(
                    scielo_issue, type(e), e
                )
            )

    def update(self, issue, issue_data, force_update):
        if self.isis_updated_date == issue.isis_updated_date:
            if not force_update:
                # nao precisa atualizar
                return
        self.isis_created_date = issue.isis_created_date
        self.isis_updated_date = issue.isis_updated_date
        self.status = MS_IMPORTED
        if issue.current_status != CURRENT:
            self.status = MS_TO_IGNORE
        self.data = issue_data
        self.save()

    class Meta:
        indexes = [
            models.Index(fields=['scielo_issue']),
            models.Index(fields=['files_status']),
            models.Index(fields=['status']),
            models.Index(fields=['isis_updated_date']),
        ]


class DocumentMigration(MigratedData):

    scielo_document = models.ForeignKey(SciELODocument, on_delete=models.CASCADE)
    files_status = models.CharField(
        _('Status'), max_length=20,
        choices=choices.MIGRATION_STATUS,
        default=choices.MS_TO_MIGRATE,
    )

    def __str__(self):
        return f"{self.scielo_document} | data: {self.status} | files: {self.files_status}"

    @classmethod
    def get_or_create(cls, scielo_document, creator):
        """
        Returns a IssueMigration (registered or new)
        """
        try:
            return cls.objects.get(
                scielo_document=scielo_document,
            )
        except cls.DoesNotExist:
            item = cls()
            item.creator = creator
            item.scielo_document = scielo_document
            item.save()
            return item
        except Exception as e:
            raise exceptions.GetOrCreateDocumentMigrationError(
                _('Unable to get_or_create_document_migration {} {} {}').format(
                    scielo_document, type(e), e
                )
            )

    def update(self, document, document_data, force_update):
        if self.isis_updated_date == document.isis_updated_date:
            if not force_update:
                # nao precisa atualizar
                return
        self.isis_created_date = document.isis_created_date
        self.isis_updated_date = document.isis_updated_date
        self.status = MS_IMPORTED
        if document.current_status != CURRENT:
            self.status = MS_TO_IGNORE
        self.data = document_data
        self.save()

    class Meta:
        indexes = [
            models.Index(fields=['scielo_document']),
            models.Index(fields=['files_status']),
            models.Index(fields=['status']),
            models.Index(fields=['isis_updated_date']),
        ]
