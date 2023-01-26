class AddLangsToXMLFilesError(Exception):
    ...


class AddPublicXMLError(Exception):
    ...


class AddSupplementaryMaterialFlagToAssetError(Exception):
    ...


class MigratedDocumentError(Exception):
    ...


class GetFilesStorageError(Exception):
    ...


class GetJournalMigratioStatusError(Exception):
    ...


class GetMigrationConfigurationError(Exception):
    ...


class GetOrCreateCrontabScheduleError(Exception):
    ...


class GetOrCreateMigratedDocumentError(Exception):
    ...


class GetOrCreateMigratedIssueError(Exception):
    ...


class GetOrCreateMigratedJournalError(Exception):
    ...


class GetSciELOIssueError(Exception):
    ...


class IssueFilesMigrationError(Exception):
    ...


class IssueFilesStoreError(Exception):
    ...


class IssueMigrationError(Exception):
    ...


class JournalMigrationError(Exception):
    ...

class JournalMigrationSaveError(Exception):
    ...


class MigrationStartError(Exception):
    ...


class PublishDocumentError(Exception):
    ...


class PublishIssueError(Exception):
    ...


class PublishJournalError(Exception):
    ...


class SetOfficialIssueToSciELOIssueError(Exception):
    ...


class GetOrCreateOfficialIssueError(Exception):
    ...
