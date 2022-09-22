import json
import os
import logging
import traceback
import sys
from datetime import datetime
from random import randint

from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.db.models import Q

from defusedxml.ElementTree import parse
from defusedxml.ElementTree import tostring as defusedxml_tostring

from packtools.sps.models.article_assets import (
    ArticleAssets,
    SupplementaryMaterials,
)
from packtools.sps.models.related_articles import (
    RelatedItems,
)
from packtools.sps.models.article_renditions import (
    ArticleRenditions,
)

# from scielo_classic_website import migration as classic_ws
from scielo_classic_website import classic_ws

from django_celery_beat.models import PeriodicTask, CrontabSchedule

from libs.dsm.files_storage.minio import MinioStorage
from libs.dsm.publication.db import mk_connection
from libs.dsm.publication.journals import JournalToPublish
from libs.dsm.publication.issues import IssueToPublish, get_bundle_id
from libs.dsm.publication.documents import DocumentToPublish

from collection.choices import CURRENT
from collection.controller import (
    JournalController,
    IssueController,
    DocumentController,
    get_scielo_journal_by_title,
    get_or_create_scielo_journal,
    get_scielo_issue_by_collection,
    get_classic_website_configuration,
)
from collection.exceptions import (
    GetSciELOJournalError,
)
from .models import (
    JournalMigration,
    IssueMigration,
    DocumentMigration,
    IssueFilesMigration,
    DocumentFilesMigration,
    MigrationFailure,
    SciELOFile,
    SciELOFileWithLang,
    SciELOHTMLFile,
    MigrationConfiguration,
)
from .choices import MS_MIGRATED, MS_PUBLISHED, MS_TO_IGNORE
from . import exceptions


User = get_user_model()
OPAC_STRING_CONNECTION = os.environ.get('OPAC_STRING_CONNECTION', 'mongodb://192.168.1.19:27017/scielo_qa')


def insert_hyphen_in_YYYYMMMDD(YYYYMMMDD):
    if YYYYMMMDD[4:6] == "00":
        return f"{YYYYMMMDD[:4]}"
    if YYYYMMMDD[6:] == "00":
        return f"{YYYYMMMDD[:4]}-{YYYYMMMDD[4:6]}"
    return f"{YYYYMMMDD[:4]}-{YYYYMMMDD[4:6]}-{YYYYMMMDD[6:]}"


def read_xml_file(file_path):
    return parse(file_path)


def tostring(xmltree):
    # garante que os diacríticos estarão devidamente representados
    return defusedxml_tostring(xmltree, encoding="utf-8").decod("utf-8")


def _register_failure(msg, e, **data):
    exc_type, exc_value, exc_traceback = sys.exc_info()
    _data = str(**data)
    logging.error(_("{} {} {}").format(msg, _data))
    logging.exception(e)
    register_failure(
        collection_acron, "migrate", "issue", issue_pid, e,
        exc_type, exc_value, exc_traceback, user_id,
    )


def register_failure(collection_acron, action_name, object_name, pid, e,
                     exc_type, exc_value, exc_traceback, user_id):
    migration_failure = MigrationFailure()
    migration_failure.collection_acron = collection_acron
    migration_failure.action_name = action_name
    migration_failure.object_name = object_name
    migration_failure.pid = pid[:23]
    migration_failure.exception_msg = str(e)[:555]
    migration_failure.traceback = [
        str(item)
        for item in traceback.extract_tb(exc_traceback)
    ]
    migration_failure.exception_type = str(type(e))
    migration_failure.creator = User.objects.get(pk=user_id)
    migration_failure.save()


def get_or_create_crontab_schedule(day_of_week=None, hour=None, minute=None):
    try:
        crontab_schedule, status = CrontabSchedule.objects.get_or_create(
            day_of_week=day_of_week or '*',
            hour=hour or '*',
            minute=minute or '*',
        )
    except Exception as e:
        raise exceptions.GetOrCreateCrontabScheduleError(
            _('Unable to get_or_create_crontab_schedule {} {} {} {} {}').format(
                day_of_week, hour, minute, type(e), e
            )
        )
    return crontab_schedule


def create_migration_starter_tasks(collection_acron, user_id):
    """
    Cria tarefas para migrar e publicar dados de title e issue

    Esta função pode ser executada ao criar `collection`
    """
    items = (
        ("title", _("Migrate and publish journals"), 'migration & publication', 1, 0, 0),
        ("title", _("Migrate journals"), 'migration', 1, 0, 0),
        ("title", _("Publish journals"), 'publication', 2, 30, 1),
        ("issue", _("Migrate and publish issues"), 'migration & publication', 3, 0, 2),
        ("issue", _("Migrate issues"), 'migration', 3, 0, 2),
        ("issue", _("Publish issues"), 'publication', 4, 30, 3),
    )

    for db_name, task, action, hours_after_now, minutes_after_now, priority in items:
        for kind in ("full", "incremental"):
            name = f'{collection_acron} | {db_name} | {action} | {kind}'
            try:
                periodic_task = PeriodicTask.objects.get(name=name)
            except PeriodicTask.DoesNotExist:
                now = datetime.utcnow()
                periodic_task = PeriodicTask()
                periodic_task.name = name
                periodic_task.task = task
                periodic_task.kwargs = json.dumps(dict(
                    collection_acron=collection_acron,
                    user_id=user_id,
                    force_update=(kind == "full"),
                ))
                if kind == "full":
                    periodic_task.priority = priority
                    periodic_task.enabled = True
                    periodic_task.one_off = True
                    periodic_task.crontab = get_or_create_crontab_schedule(
                        hour=(now.hour + hours_after_now) % 24,
                        minute=now.minute,
                    )
                else:
                    periodic_task.priority = priority
                    periodic_task.enabled = True
                    periodic_task.one_off = False
                    periodic_task.crontab = get_or_create_crontab_schedule(
                        minute=(now.minute + minutes_after_now) % 60,
                    )
                periodic_task.save()


# def create_tasks_to_migrate_issues_components(collection_acron, user_id):
#     """
#     Cria tarefas periódicas para migrar issues files por journal acron
#     distribuídas em 1h a 24h após a execução desta função
#     """
#     logging.info("create_tasks_to_migrate_issues_components")
#     try:
#         name = f'{collection_acron} | issue | migration | full'
#         periodic_task = PeriodicTask.objects.get(name=name)
#         from_hour = int(periodic_task.crontab.hour) + 1
#     except PeriodicTask.DoesNotExist:
#         from_hour = datetime.utcnow().hour

#     base_kwargs = dict(
#         collection_acron=collection_acron,
#         user_id=user_id,
#         force_update=True,
#     )

#     items = (
#         (
#             "issues files & documents",
#             _('Migrate issues files | Migrate documents | Publish documents'),
#             'migrations & publication',
#             from_hour + 1
#             ),
#         (
#             "issues files",
#             _('Migrate issues files'),
#             'migration',
#             from_hour + 1
#             ),
#         (
#             "documents",
#             _('Migrate documents'),
#             'migration',
#             from_hour + 3,
#             ),
#         (
#             "documents",
#             _('Publish documents'),
#             'publication',
#             from_hour + 5,
#             ),
#     )

#     for migration in IssueMigration.objects.all():

#         journal_acron = migration.scielo_issue.scielo_journal.acron
#         scielo_issn = migration.scielo_issue.scielo_journal.scielo_issn
#         publication_year = migration.scielo_issue.pub_year

#         kwargs_sets = (
#             {"scielo_issn": scielo_issn, "publication_year": publication_year},
#             {"scielo_issn": scielo_issn},
#             {"publication_year": publication_year},
#         )

#         for component, task, action, hour in items:
#             hour = hour % 24
#             minute = randint(0, 59)

#             name_parts_sets = (
#                 (collection_acron, component, journal_acron, publication_year, action, ),
#                 (collection_acron, component, journal_acron, action, ),
#                 (collection_acron, component, publication_year, action, ),
#             )

#             for parms, name_parts in zip(kwargs_sets, name_parts_sets):
#                 kwargs = base_kwargs
#                 kwargs.update(parms)

#                 name = ' | '.join(name_parts)
#                 logging.info(name)
#                 try:
#                     periodic_task = PeriodicTask.objects.get(name=name)
#                 except PeriodicTask.DoesNotExist:
#                     now = datetime.utcnow()
#                     periodic_task = PeriodicTask()
#                     periodic_task.name = name
#                     periodic_task.task = task
#                     periodic_task.kwargs = kwargs
#                     
#                     periodic_task.enabled = True
#                     periodic_task.one_off = True
#                     periodic_task.crontab = get_or_create_crontab_schedule(
#                         hour=hour,
#                         minute=minute,
#                     )
#                     periodic_task.save()

def create_tasks_to_migrate_issues_components(collection_acron, user_id):
    """
    Cria tarefas periódicas para migrar issues files por journal acron
    distribuídas em 1h a 24h após a execução desta função
    """
    logging.info("create_tasks_to_migrate_issues_components")
    try:
        name = f'{collection_acron} | issue | migration | full'
        periodic_task = PeriodicTask.objects.get(name=name)
        from_hour = int(periodic_task.crontab.hour) + 1
    except PeriodicTask.DoesNotExist:
        from_hour = datetime.utcnow().hour

    base_kwargs = dict(
        collection_acron=collection_acron,
        user_id=user_id,
        force_update=True,
    )

    items = (
        (
            "artigo",
            _('Migrate and publish documents'),
            'migrations & publication',
            from_hour + 1
            ),
    )

    for migration in IssueMigration.objects.all():

        journal_acron = migration.scielo_issue.scielo_journal.acron
        scielo_issn = migration.scielo_issue.scielo_journal.scielo_issn
        publication_year = migration.scielo_issue.pub_year

        kwargs_sets = (
            {"scielo_issn": scielo_issn, "publication_year": publication_year},
            {"scielo_issn": scielo_issn},
            {"publication_year": publication_year},
        )

        for component, task, action, hour in items:
            hour = hour % 24
            minute = randint(0, 59)

            name_parts_sets = (
                (collection_acron, component, journal_acron, publication_year, action, ),
                (collection_acron, component, journal_acron, action, ),
                (collection_acron, component, publication_year, action, ),
            )

            for parms, name_parts in zip(kwargs_sets, name_parts_sets):
                kwargs = base_kwargs
                kwargs.update(parms)

                for kind in ("full", "incremental"):
                    kwargs['force_update'] = (kind == "full")

                    name = ' | '.join(name_parts) + " | " + kind
                    logging.info(name)
                    try:
                        periodic_task = PeriodicTask.objects.get(name=name)
                    except PeriodicTask.DoesNotExist:
                        now = datetime.utcnow()
                        periodic_task = PeriodicTask()
                        periodic_task.name = name
                        periodic_task.task = task
                        periodic_task.kwargs = json.dumps(kwargs)
                        periodic_task.priority = 4 if kind == "full" else 5
                        periodic_task.enabled = True
                        periodic_task.one_off = (kind == "full")
                        periodic_task.crontab = get_or_create_crontab_schedule(
                            hour=hour,
                            minute=minute,
                        )
                        periodic_task.save()


def get_or_create_journal_migration(scielo_journal, creator_id):
    """
    Returns a JournalMigration (registered or new)
    """
    try:
        jm, created = JournalMigration.objects.get_or_create(
            scielo_journal=scielo_journal,
            creator_id=creator_id,
        )
    except Exception as e:
        raise exceptions.GetOrCreateJournalMigrationError(
            _('Unable to get_or_create_journal_migration {} {} {}').format(
                scielo_journal, type(e), e
            )
        )
    return jm


def get_journal_migration_status(scielo_issn):
    """
    Returns a JournalMigration status
    """
    try:
        return JournalMigration.objects.get(
            scielo_journal__scielo_issn=scielo_issn,
        ).status
    except Exception as e:
        raise exceptions.GetJournalMigratioStatusError(
            _('Unable to get_journal_migration_status {} {} {}').format(
                scielo_issn, type(e), e
            )
        )


class MigrationConfigurationController:

    def __init__(self, collection_acron):
        try:
            self._config = MigrationConfiguration.objects.get(
                classic_website_config__collection__acron=collection_acron)
        except Exception as e:
            self._config = None
            # raise exceptions.GetMigrationConfigurationError(
            #     _('Unable to get_migration_configuration {} {} {}').format(
            #         collection_acron, type(e), e
            #     )
            # )

    def connect_db(self, default=None):
        try:
            return mk_connection(
                default or self._config.new_website_config.db_uri)

        except Exception as e:
            raise exceptions.GetMigrationConfigurationError(
                _("Unable to connect db {} {}").format(type(e), e)
            )

    @property
    def classic_website(self):
        try:
            return self._config.classic_website_config

        except Exception as e:
            raise exceptions.GetMigrationConfigurationError(
                _("Unable to get classic website configuration {} {}").format(
                    type(e), e)
            )

    def get_classic_website_paths(self, default=None):
        try:
            if default or not hasattr(self, '_classic_website_paths') and not self._classic_website_paths:
                self._classic_website_paths = default or {
                    "BASES_TRANSLATION_PATH": self.classic_website.bases_translation_path,
                    "BASES_PDF_PATH": self.classic_website.bases_pdf_path,
                    "HTDOCS_IMG_REVISTAS_PATH": self.classic_website.htdocs_img_revistas_path,
                    "BASES_XML_PATH": self.classic_website.bases_xml_path,
                }
        except Exception as e:
            raise exceptions.GetMigrationConfigurationError(
                _("Unable to get classic website paths {} {}").format(
                    type(e), e)
            )
        return self._classic_website_paths

    def get_source_file_path(self, db_name, default):
        try:
            return default or getattr(self.classic_website, f'{db_name}_path')
        except AttributeError:
            return None

    def get_artigo_source_files_paths(self, journal_acron, issue_folder, default):
        if default:
            return [default]
        return self._get_artigo_file_path(journal_acron, issue_folder)

    def _get_artigo_files_paths(self, j_acron, issue_folder):
        items = []
        _serial_path = os.path.join(
            self.classic_website.serial_path,
            j_acron, issue_folder, "base_xml", "id")

        if os.path.isdir(_serial_path):
            items.append(os.path.join(_serial_path, "i.id"))
            for item in os.listdir(_serial_path):
                if item != 'i.id' and item.endswith(".id"):
                    items.append(os.path.join(_serial_path, item))

        if not items:
            _bases_work_path = os.path.join(
                self.classic_website.bases_work_path, j_acron, j_acron,
            )
            source_file_path = classic_ws.get_bases_work_acron_path(
                self.classic_website.cisis_path,
                _bases_work_path,
                issue_folder,
            )
            items.append(source_file_path)
        return items

    def get_files_storage(self, default=None):
        if default or not hasattr(self, '_files_storage') and not self._files_storage:
            try:
                files_storage_config = default or self._config.files_storage_config
                self._bucket_public_subdir = files_storage_config.bucket_public_subdir
                self._bucket_migration_subdir = files_storage_config.bucket_migration_subdir
                self._files_storage = MinioStorage(
                    minio_host=files_storage_config.host,
                    minio_access_key=files_storage_config.access_key,
                    minio_secret_key=files_storage_config.secret_key,
                    bucket_root=files_storage_config.bucket_root,
                    bucket_subdir=(
                        files_storage_config.bucket_subdir or
                        files_storage_config.bucket_public_subdir),
                    minio_secure=files_storage_config.secure,
                    minio_http_client=None,
                )
            except AttributeError:
                try:
                    self._bucket_public_subdir = files_storage_config["bucket_public_subdir"]
                    self._bucket_migration_subdir = files_storage_config["bucket_migration_subdir"]
                    self._files_storage = MinioStorage(
                        minio_host=files_storage_config["host"],
                        minio_access_key=files_storage_config["access_key"],
                        minio_secret_key=files_storage_config["secret_key"],
                        bucket_root=files_storage_config["bucket_root"],
                        bucket_subdir=(
                            files_storage_config.get("bucket_subdir") or
                            files_storage_config["bucket_public_subdir"]),
                        minio_secure=files_storage_config.get("secure"),
                        minio_http_client=None,
                    )
                except Exception as e:
                    raise exceptions.GetFilesStorageError(
                        _("Unable to get MinioStorage {} {} {}").format(
                            files_storage_config, type(e), e)
                    )
        return self._files_storage

    def store_issue_files(self, journal_acron, issue_folder):
        try:
            issue_files = classic_ws.get_issue_files(
                journal_acron, issue_folder, self.get_classic_website_paths())
        except Exception as e:
            raise exceptions.IssueFilesStoreError(
                _("Unable to get issue files from classic website {} {} {}").format(
                    journal_acron, issue_folder, e,
                )
            )
        for info in issue_files:
            try:
                mimetype = None
                name, ext = os.path.splitext(info['path'])
                if ext in (".xml", ".html", ".htm"):
                    subdir = self._bucket_migration_subdir
                    mimetype = "text/xml" if ext == ".xml" else "html"
                else:
                    subdir = self._bucket_public_subdir
                subdirs = os.path.join(
                    subdir, journal_acron, issue_folder,
                )
                logging.info(info['path'])
                response = self._files_storage.register(
                    info['path'], subdirs=subdirs, preserve_name=True)
                info.update(response)
                yield info

            except Exception as e:
                raise exceptions.IssueFilesStoreError(
                    _("Unable to store issue files {} {} {}").format(
                        journal_acron, issue_folder, e,
                    )
                )


def migrate_and_publish_journals(
        user_id,
        collection_acron,
        source_file_path=None,
        force_update=False,
        db_uri=None,
        ):
    try:
        mcc = MigrationConfigurationController(collection_acron)
        mcc.connect_db(db_uri)
        source_file_path = mcc.get_source_file_path("title", source_file_path)

        for scielo_issn, journal_data in classic_ws.get_records_by_source_path("title", source_file_path):
            try:
                action = "migrate"
                journal_migration = migrate_journal(
                    user_id, collection_acron,
                    scielo_issn, journal_data[0], force_update)
                publish_migrated_journal(journal_migration)
            except Exception as e:
                logging.error(_("Error migrating journal {} {}").format(collection_acron, scielo_issn))
                logging.exception(e)
                exc_type, exc_value, exc_traceback = sys.exc_info()
                register_failure(
                    collection_acron, action, "journal", scielo_issn, e,
                    exc_type, exc_value, exc_traceback, user_id,
                )
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        register_failure(
            collection_acron, "migrate and publish", "journal", "GENERAL", e,
            exc_type, exc_value, exc_traceback, user_id,
        )


def migrate_journals(user_id,
                     collection_acron,
                     source_file_path=None,
                     force_update=False,
                     ):

    try:
        mcc = MigrationConfigurationController(collection_acron)
        source_file_path = mcc.get_source_file_path("title", source_file_path)

        for scielo_issn, journal_data in classic_ws.get_records_by_source_path("title", source_file_path):
            try:
                migrate_journal(user_id, collection_acron,
                                scielo_issn, journal_data[0], force_update)
            except Exception as e:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                register_failure(
                    collection_acron, "migrate", "journal", scielo_issn, e,
                    exc_type, exc_value, exc_traceback, user_id,
                )
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        register_failure(
            collection_acron, "migrate", "journal", "GENERAL", e,
            exc_type, exc_value, exc_traceback, user_id,
        )


def migrate_journal(user_id, collection_acron, scielo_issn, journal_data,
                    force_update=False):
    """
    Create/update JournalMigration
    """
    journal = classic_ws.Journal(journal_data)
    journal_controller = JournalController(
        user_id=user_id,
        collection_acron=collection_acron,
        scielo_issn=scielo_issn,
        issn_l=None,
        e_issn=journal.electronic_issn,
        print_issn=journal.print_issn,
        journal_acron=journal.acronym,
    )
    journal_migration = get_or_create_journal_migration(
        journal_controller.scielo_journal, creator_id=user_id)

    if not journal_controller.scielo_journal.publication_status or not journal_controller.scielo_journal.title:
        if not journal_controller.scielo_journal.publication_status:
            journal_controller.scielo_journal.publication_status = journal.publication_status
        if not journal_controller.scielo_journal.title:
            journal_controller.scielo_journal.title = journal.title
        journal_controller.scielo_journal.save()

    # check if it needs to be update
    if journal_migration.isis_updated_date == journal.isis_updated_date:
        if not force_update:
            # nao precisa atualizar
            return journal_migration
    try:
        journal_migration.isis_created_date = journal.isis_created_date
        journal_migration.isis_updated_date = journal.isis_updated_date
        journal_migration.status = MS_MIGRATED
        if journal.publication_status != CURRENT:
            journal_migration.status = MS_TO_IGNORE
        journal_migration.data = journal_data
        journal_migration.save()
        return journal_migration
    except Exception as e:
        raise exceptions.JournalMigrationSaveError(
            _("Unable to save journal migration {} {} {}").format(
                collection_acron, scielo_issn, e
            )
        )


def publish_migrated_journals(
        user_id,
        collection_acron,
        db_uri=None,
        ):
    try:
        mcc = MigrationConfigurationController(collection_acron)
        mcc.connect_db(db_uri)

        for journal_migration in JournalMigration.objects.filter(
                scielo_journal__collection__acron=collection_acron,
                scielo_journal__publication_status=CURRENT,
                status=MS_MIGRATED,
                ):

            try:
                publish_migrated_journal(journal_migration)
            except Exception as e:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                register_failure(
                    collection_acron, "publication", "journal",
                    journal_migration.scielo_journal.scielo_issn, e,
                    exc_type, exc_value, exc_traceback, user_id,
                )

    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        register_failure(
            collection_acron, "publication", "journal",
            "GENERAL", e,
            exc_type, exc_value, exc_traceback, user_id,
        )


def publish_migrated_journal(journal_migration):
    journal = classic_ws.Journal(journal_migration.data)
    if journal.publication_status != CURRENT:
        # journal must not be published
        return

    if journal_migration.status != MS_MIGRATED:
        return

    try:
        journal_to_publish = JournalToPublish(journal.scielo_issn)
        journal_to_publish.add_contact(
            " | ".join(journal.publisher_name),
            journal.publisher_email,
            ", ".join(journal.publisher_address),
            journal.publisher_city,
            journal.publisher_state,
            journal.publisher_country,
        )

        for mission in journal.mission:
            journal_to_publish.add_item_to_mission(
                mission["language"], mission["text"])

        for item in journal.status_history:
            journal_to_publish.add_item_to_timeline(
                item["status"],
                insert_hyphen_in_YYYYMMMDD(item["date"]),
                item.get("reason"),
            )
        journal_to_publish.add_journal_issns(
            journal.scielo_issn,
            journal.electronic_issn,
            journal.print_issn,
        )
        journal_to_publish.add_journal_titles(
            journal.title,
            journal.abbreviated_iso_title,
            journal.abbreviated_title,
        )

        journal_to_publish.add_online_submission_url(journal.submission_url)

        # TODO links previous e next
        # previous_journal = next_journal_title = None
        # if journal.previous_title:
        #     try:
        #         previous_journal = get_scielo_journal_by_title(
        #             journal.previous_title)
        #     except GetSciELOJournalError:
        #         previous_journal = None
        # if journal.next_title:
        #     try:
        #         next_journal = get_scielo_journal_by_title(journal.next_title)
        #         next_journal_title = journal.next_title
        #     except GetSciELOJournalError:
        #         next_journal_title = None
        # if previous_journal or next_journal_title:
        #     journal_to_publish.add_related_journals(
        #         previous_journal, next_journal_title,
        #     )
        for item in journal.sponsors:
            journal_to_publish.add_sponsor(item)

        # TODO confirmar se subject_categories é subject_descriptors
        journal_to_publish.add_thematic_scopes(
            journal.subject_descriptors, journal.subject_areas,
        )

        # journal não tem este dado
        # journal_to_publish.add_issue_count(
        #     journal.issue_count,
        # )

        # journal não tem este dado
        # journal_to_publish.add_item_to_metrics(
        #     journal.total_h5_index,
        #     journal.total_h5_median,
        #     journal.h5_metric_year,
        # )
        # journal não tem este dado
        # journal_to_publish.add_logo_url(journal.logo_url)
        journal_to_publish.add_acron(journal.acronym)
        journal_to_publish.publish_journal()
    except Exception as e:
        raise exceptions.PublishJournalError(
            _("Unable to publish {} {} {}").format(
                journal_migration, type(e), e)
        )

    try:
        journal_migration.status = MS_PUBLISHED
        journal_migration.save()
    except Exception as e:
        raise exceptions.PublishJournalError(
            _("Unable to publish {} {} {}").format(
                journal_migration, type(e), e)
        )


def get_or_create_issue_migration(scielo_issue, creator_id):
    """
    Returns a IssueMigration (registered or new)
    """
    try:
        jm, created = IssueMigration.objects.get_or_create(
            scielo_issue=scielo_issue,
            creator_id=creator_id,
        )
        jm.save()
    except Exception as e:
        raise exceptions.GetOrCreateIssueMigrationError(
            _('Unable to get_or_create_issue_migration {} {} {}').format(
                scielo_issue, type(e), e
            )
        )
    return jm


def migrate_and_publish_issues(
        user_id,
        collection_acron,
        source_file_path=None,
        force_update=False,
        db_uri=None,
        ):
    try:
        mcc = MigrationConfigurationController(collection_acron)
        mcc.connect_db(db_uri)
        source_file_path = mcc.get_source_file_path("issue", source_file_path)

        for issue_pid, issue_data in classic_ws.get_records_by_source_path("issue", source_file_path):
            try:
                action = "migrate"
                issue_migration = migrate_issue(
                    user_id=user_id,
                    collection_acron=collection_acron,
                    scielo_issn=issue_pid[:9],
                    issue_pid=issue_pid,
                    issue_data=issue_data[0],
                    force_update=force_update,
                )
                publish_migrated_issue(issue_migration, force_update)
            except Exception as e:
                logging.error(_("Error migrating issue {} {}").format(collection_acron, issue_pid))
                logging.exception(e)
                exc_type, exc_value, exc_traceback = sys.exc_info()
                register_failure(
                    collection_acron, action, "issue", issue_pid, e,
                    exc_type, exc_value, exc_traceback, user_id,
                )
    except Exception as e:
        raise e
        exc_type, exc_value, exc_traceback = sys.exc_info()
        register_failure(
            collection_acron, "migrate and publish", "issue", "GENERAL", e,
            exc_type, exc_value, exc_traceback, user_id,
        )


def migrate_issues(
        user_id,
        collection_acron,
        source_file_path=None,
        force_update=False,
        ):

    try:
        mcc = MigrationConfigurationController(collection_acron)
        source_file_path = mcc.get_source_file_path("issue", source_file_path)

        for issue_pid, issue_data in classic_ws.get_records_by_source_path("issue", source_file_path):
            try:
                if get_journal_migration_status(issue_pid[:9]) != MS_PUBLISHED and not force_update:
                    continue
                migrate_issue(
                    user_id=user_id,
                    collection_acron=collection_acron,
                    scielo_issn=issue_pid[:9],
                    issue_pid=issue_pid,
                    issue_data=issue_data[0],
                    force_update=force_update,
                )
            except Exception as e:
                logging.error(_("Error migrating issue {} {}").format(collection_acron, issue_pid))
                logging.exception(e)
                exc_type, exc_value, exc_traceback = sys.exc_info()
                register_failure(
                    collection_acron, "migrate", "issue", issue_pid, e,
                    exc_type, exc_value, exc_traceback, user_id,
                )
    except Exception as e:
        logging.error(_("Error migrating issue {}").format(collection_acron))
        logging.exception(e)
        exc_type, exc_value, exc_traceback = sys.exc_info()
        register_failure(
            collection_acron, "migrate", "issue", "GENERAL", e,
            exc_type, exc_value, exc_traceback, user_id,
        )
        return


def migrate_issue(
        user_id,
        collection_acron,
        scielo_issn,
        issue_pid,
        issue_data,
        force_update=False,
        ):
    """
    Create/update IssueMigration
    """
    issue = classic_ws.Issue(issue_data)

    issue_controller = IssueController(
        user_id=user_id,
        collection_acron=collection_acron,
        scielo_issn=scielo_issn,
        year=issue.publication_year,
        volume=issue.volume,
        number=issue.number,
        supplement=issue.suppl,
        issue_pid=issue_pid,
        is_press_release=issue.is_press_release,
    )

    issue_migration = get_or_create_issue_migration(
        issue_controller.scielo_issue, creator_id=user_id)

    if not issue_controller.scielo_issue.pub_year:
        issue_controller.scielo_issue.pub_year = issue.publication_year
        issue_controller.scielo_issue.save()

    # check if it needs to be update
    if issue_migration.isis_updated_date == issue.isis_updated_date:
        if not force_update:
            # nao precisa atualizar
            return issue_migration
    try:
        issue_migration.isis_created_date = issue.isis_created_date
        issue_migration.isis_updated_date = issue.isis_updated_date
        issue_migration.status = MS_MIGRATED
        if issue.is_press_release:
            issue_migration.status = MS_TO_IGNORE
        issue_migration.data = issue_data

        issue_migration.save()
        return issue_migration
    except Exception as e:
        logging.error(_("Error migrating issue {} {}").format(collection_acron, issue_pid))
        logging.exception(e)
        raise exceptions.IssueMigrationSaveError(
            _("Unable to save {} migration {} {} {}").format(
                "issue", collection_acron, issue_pid, e
            )
        )


def publish_migrated_issues(
        user_id,
        collection_acron,
        db_uri=None,
        ):

    try:
        mcc = MigrationConfigurationController(collection_acron)
        mcc.connect_db(db_uri)

        for issue_migration in IssueMigration.objects.filter(
                scielo_issue__scielo_journal__collection__acron=collection_acron,
                status=MS_MIGRATED,
                ):

            try:
                publish_migrated_issue(issue_migration)
            except Exception as e:
                logging.error(_("Error publishing issue {}").format(issue_migration))
                logging.exception(e)
                exc_type, exc_value, exc_traceback = sys.exc_info()
                register_failure(
                    collection_acron, "publication", "issue",
                    issue_migration.scielo_issue.issue_pid, e,
                    exc_type, exc_value, exc_traceback, user_id,
                )

    except Exception as e:
        logging.error(_("Error publishing issue"))
        logging.exception(e)
        exc_type, exc_value, exc_traceback = sys.exc_info()
        register_failure(
            collection_acron, "publication", "issue",
            "GENERAL", e,
            exc_type, exc_value, exc_traceback, user_id,
        )


def publish_migrated_issue(issue_migration, force_update):
    """
    Raises
    ------
    PublishIssueError
    """
    issue = classic_ws.Issue(issue_migration.data)

    if issue_migration.status != MS_MIGRATED and not force_update:
        return
    try:
        published_id = get_bundle_id(
            issue.journal,
            issue.publication_year,
            issue.volume,
            issue.number,
            issue.supplement,
        )
        issue_to_publish = IssueToPublish(published_id)

        issue_to_publish.add_identification(
            issue.volume,
            issue.number,
            issue.supplement)
        issue_to_publish.add_journal(issue.journal)
        issue_to_publish.add_order(int(issue.order[4:]))
        issue_to_publish.add_pid(issue.pid)
        issue_to_publish.add_publication_date(
            issue.publication_year,
            issue.start_month,
            issue.end_month)
        # FIXME indica se há artigos / documentos
        issue_to_publish.has_docs = []

        issue_to_publish.publish_issue()
    except Exception as e:
        raise exceptions.PublishIssueError(
            _("Unable to publish {} {}").format(
                issue_migration.scielo_issue.issue_pid, e)
        )

    try:
        issue_migration.status = MS_PUBLISHED
        issue_migration.save()
    except Exception as e:
        raise exceptions.PublishIssueError(
            _("Unable to upate issue_migration status {} {}").format(
                issue_migration.scielo_issue.issue_pid, e)
        )


def get_or_create_issue_files_migration(scielo_issue, creator_id):
    """
    Returns a IssueMigration (registered or new)
    """
    try:
        jm, created = IssueFilesMigration.objects.get_or_create(
            scielo_issue=scielo_issue,
            creator_id=creator_id,
        )
    except Exception as e:
        raise exceptions.GetOrCreateIssueFilesMigrationError(
            _('Unable to get_or_create_issue_files_migration {} {} {}').format(
                scielo_issue, type(e), e
            )
        )
    return jm


def migrate_issues_files(
        user_id,
        collection_acron,
        scielo_issn=None,
        publication_year=None,
        files_storage_config=None,
        classic_ws_config=None,
        force_update=None,
        ):

    if scielo_issn and publication_year:
        items = IssueMigration.objects.filter(
            Q(status=MS_PUBLISHED) | Q(status=MS_MIGRATED),
            scielo_issue__scielo_journal__collection__acron=collection_acron,
            scielo_issue__scielo_journal__scielo_issn=scielo_issn,
            scielo_issue__pub_year=publication_year,
            )
    elif scielo_issn:
        items = IssueMigration.objects.filter(
            Q(status=MS_PUBLISHED) | Q(status=MS_MIGRATED),
            scielo_issue__scielo_journal__collection__acron=collection_acron,
            scielo_issue__scielo_journal__scielo_issn=scielo_issn,
            )
    elif publication_year:
        items = IssueMigration.objects.filter(
            Q(status=MS_PUBLISHED) | Q(status=MS_MIGRATED),
            scielo_issue__scielo_journal__collection__acron=collection_acron,
            scielo_issue__pub_year=publication_year,
            )
    else:
        items = IssueMigration.objects.filter(
            Q(status=MS_PUBLISHED) | Q(status=MS_MIGRATED),
            scielo_issue__scielo_journal__collection__acron=collection_acron,
            )

    mcc = MigrationConfigurationController(collection_acron)
    mcc.get_classic_website_paths(classic_ws_config)
    mcc.get_files_storage(files_storage_config)

    for issue_migration in items:
        try:
            issue_files_migration = migrate_issue_files(
                user_id=user_id,
                issue_migration=issue_migration,
                store_issue_files=mcc.store_issue_files,
                force_update=force_update,
            )
        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            register_failure(
                collection_acron, "migrate_files", "issue",
                issue_migration.scielo_issue.issue_pid, e,
                exc_type, exc_value, exc_traceback, user_id,
            )


def migrate_issue_files(
        user_id,
        issue_migration,
        store_issue_files,
        force_update,
        ):
    """
    Create/update IssueFilesMigration
    """
    scielo_issue = issue_migration.scielo_issue
    issue_files_migration = get_or_create_issue_files_migration(
        scielo_issue, creator_id=user_id)

    if issue_files_migration.status == MS_MIGRATED and not force_update:
        return issue_files_migration

    try:
        issue = classic_ws.Issue(issue_migration.data)
        for item in store_issue_files(
                scielo_issue.scielo_journal.acron,
                scielo_issue.issue_folder,
                ):
            item['file_id'] = item.pop('key')
            type = item.pop('type')
            if type == "pdf":
                ClassFile = SciELOFileWithLang
                files = issue_files_migration.pdfs
            elif type == "html":
                ClassFile = SciELOHTMLFile
                files = issue_files_migration.htmls
            elif type == "xml":
                ClassFile = SciELOFile
                files = issue_files_migration.xmls
            else:
                ClassFile = SciELOFile
                files = issue_files_migration.assets

            params = {
                k: item[k]
                for k in item.keys()
                if hasattr(ClassFile, k)
            }
            files.add(ClassFile(**params))

        issue_files_migration.status = MS_MIGRATED
        issue_files_migration.save()
        return issue_files_migration
    except Exception as e:
        raise exceptions.IssueFilesMigrationSaveError(
            _("Unable to save issue files migration {} {}").format(
                scielo_issue, e)
        )


##########################################################################


def get_or_create_document_migration(scielo_document, creator_id):
    """
    Returns a DocumentMigration (registered or new)
    """
    try:
        jm, created = DocumentMigration.objects.get_or_create(
            scielo_document=scielo_document,
            creator_id=creator_id,
        )
    except Exception as e:
        raise exceptions.GetOrCreateDocumentMigrationError(
            _('Unable to get_or_create_document_migration {} {} {}').format(
                scielo_document, type(e), e
            )
        )
    return jm


def get_or_create_document_files_migration(scielo_document, creator_id):
    """
    Returns a DocumentFilesMigration (registered or new)
    """
    try:
        document_files_migration, created = DocumentFilesMigration.objects.get_or_create(
            scielo_document=scielo_document,
            creator_id=creator_id,
        )
    except Exception as e:
        raise exceptions.GetOrCreateDocumentFilesMigrationError(
            _('Unable to get_or_create_document_files_migration {} {} {}').format(
                scielo_document, type(e), e
            )
        )
    return document_files_migration


def migrate_issue_files_and_documents__and__publish_documents(
        user_id,
        collection_acron,
        scielo_issn=None,
        publication_year=None,
        files_storage_config=None,
        classic_ws_config=None,
        db_uri=None,
        source_file_path=None,
        force_update=False,
        ):

    if scielo_issn and publication_year:
        items = IssueMigration.objects.filter(
            Q(status=MS_PUBLISHED) | Q(status=MS_MIGRATED),
            scielo_issue__scielo_journal__collection__acron=collection_acron,
            scielo_issue__scielo_journal__scielo_issn=scielo_issn,
            scielo_issue__pub_year=publication_year,
            )
    elif scielo_issn:
        items = IssueMigration.objects.filter(
            Q(status=MS_PUBLISHED) | Q(status=MS_MIGRATED),
            scielo_issue__scielo_journal__collection__acron=collection_acron,
            scielo_issue__scielo_journal__scielo_issn=scielo_issn,
            )
    elif publication_year:
        items = IssueMigration.objects.filter(
            Q(status=MS_PUBLISHED) | Q(status=MS_MIGRATED),
            scielo_issue__scielo_journal__collection__acron=collection_acron,
            scielo_issue__pub_year=publication_year,
            )
    else:
        items = IssueMigration.objects.filter(
            Q(status=MS_PUBLISHED) | Q(status=MS_MIGRATED),
            scielo_issue__scielo_journal__collection__acron=collection_acron,
            )

    mcc = MigrationConfigurationController(collection_acron)
    mcc.connect_db(db_uri)
    mcc.get_classic_website_paths(classic_ws_config)
    files_storage = mcc.get_files_storage(files_storage_config)
    publication_subdir = mcc._bucket_public_subdir

    for issue_migration in items:
        try:
            issue_files_migration = migrate_issue_files(
                user_id=user_id,
                issue_migration=issue_migration,
                store_issue_files=mcc.store_issue_files,
                force_update=force_update,
            )

            for source_file_path in mcc.get_artigo_source_files_paths(
                    issue_migration.scielo_issue.scielo_journal.acron,
                    issue_migration.scielo_issue.issue_folder,
                    source_file_path,
                    ):
                migrate_documents(
                    user_id,
                    collection_acron,
                    source_file_path,
                    files_storage,
                    publication_subdir,
                    issue_files_migration,
                    force_update,
                )

        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            register_failure(
                collection_acron, "migrate", "document",
                issue_migration.scielo_issue.issue_pid, e,
                exc_type, exc_value, exc_traceback, user_id,
            )


def migrate_documents(
        user_id,
        collection_acron,
        source_file_path,
        files_storage,
        publication_subdir,
        issue_files_migration,
        force_update=False,
        ):

    try:
        scielo_issue = None
        for pid, document_data in classic_ws.get_records_by_source_path(
                "artigo", source_file_path):
            try:
                document = classic_ws.Document(document_data)

                scielo_issue = (
                    scielo_issue or
                    get_scielo_issue_by_collection(collection_acron, pid[1:-5])
                )
                scielo_document = get_or_create_scielo_document(
                    scielo_issue,
                    pid,
                    document.filename_without_extension,
                    user_id,
                )
                document_migration = get_or_create_document_migration(
                    scielo_document=scielo_document,
                    creator_id=_user_id,
                )
                document_files_migration = get_or_create_document_files_migration(
                    scielo_document=scielo_document,
                    creator_id=_user_id,
                )
                document_files_controller = DocumentFilesController(
                    files_storage=files_storage,
                    issue_files_migration=issue_files_migration,
                    publication_subdir=publication_subdir,
                    file_id=document.filename_without_extension,
                )

                migrate_document(
                    pid, document_data, document_migration,
                    document_files_controller, force_update,
                )

                migrate_document_files(
                    document_files_migration,
                    document_files_controller,
                    force_update,
                )

                publish_document(
                    pid, document, document_migration,
                    document_files_migration,
                )

            except Exception as e:
                exc_type, exc_value, exc_traceback = sys.exc_info()
                logging.exception(
                    "Error migrating document %s %s %s %s " %
                    (document_pid, exc_type, exc_value, exc_traceback)
                )
                register_failure(
                    collection_acron, "migrate", "document", pid, e,
                    exc_type, exc_value, exc_traceback, user_id,
                )
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        register_failure(
            collection_acron, "migrate", "document", "GENERAL", e,
            exc_type, exc_value, exc_traceback, user_id,
        )
        return


def migrate_document(pid, document_data, document_migration, document_files_controller, force_update=False):
    """
    Create/update DocumentMigration

    """
    # check if it needs to be update
    if document_migration.isis_updated_date == document.isis_updated_date:
        if not force_update:
            # nao precisa atualizar
            return
    try:
        document_migration.isis_created_date = document.isis_created_date
        document_migration.isis_updated_date = document.isis_updated_date
        document_migration.status = MS_MIGRATED
        document_migration.data = document_data
        document_migration.text_langs = document_files_controller.text_langs
        document_migration.related_items = document_files_controller.related_items
        document_migration.save()
    except Exception as e:
        raise exceptions.DocumentMigrationSaveError(
            _("Unable to save document migration {} {}").format(
                pid, e
            )
        )


def migrate_document_files(document_files_migration, document_files_controller, force_update=False):
    """
    Create/update DocumentFilesMigration

    """
    # check if it needs to be update
    if document_files_migration.status == MS_MIGRATED:
        if not force_update:
            # nao precisa atualizar
            return
    try:
        document_files_migration.suppl_mats = (
            document_files_controller.suppl_mats
        )
        document_files_migration.xmls = (
            document_files_controller.xmls
        )
        document_files_migration.htmls = (
            document_files_controller.htmls
        )
        document_files_migration.pdfs = (
            document_files_controller.pdfs
        )
        document_files_migration.assets = (
            document_files_controller.assets
        )

        if document_files_migration.xmls:
            document_files_migration.status = MS_MIGRATED

        document_files_migration.save()
    except Exception as e:
        raise exceptions.DocumentFilesMigrationSaveError(
            _("Unable to save document files migration {} {}").format(
                document_files_migration, e)
        )


def publish_document(pid, document, document_migration, document_files_migration):
    """
    Raises
    ------
    PublishDocumentError
    """
    doc_to_publish = DocumentToPublish(pid)

    if doc_to_publish.created:
        return
        # raise exceptions.DocumentPublicationForbiddenError(
        #     _(
        #         "Forbidden to publish migrated document {} automatically, "
        #         "because it must be updated by the Upload System workflow"
        #     ).format(pid)
        # )

    if document_migration.status != MS_MIGRATED:
        return
        # raise exceptions.DocumentPublicationForbiddenError(
        #     _(
        #         "Unable to publish migrated document {}, "
        #         "because DocumentMigration.status is not MIGRATED"
        #     ).format(pid)
        # )

    if document_files_migration.status != MS_MIGRATED:
        return
        # raise exceptions.DocumentPublicationForbiddenError(
        #     _(
        #         "Unable to publish migrated document {}, "
        #         "because DocumentFilesMigration.status is not MIGRATED"
        #     ).format(pid)
        # )

    try:
        # IDS
        doc_to_publish.add_identifiers(
            document.scielo_pid_v3,
            document.scielo_pid_v2,
            document.publisher_ahead_id,
        )

        # MAIN METADATA
        doc_to_publish.add_document_type(document.document_type)
        doc_to_publish.add_main_metadata(
            document.title,
            document.section,
            document.abstract,
            document.lang,
            document.doi,
        )
        for item in document.authors:
            doc_to_publish.add_author_meta(
                item['surname'], item['given_names'],
                item.get("suffix"),
                item.get("affiliation"),
                item.get("orcid"),
            )

        # ISSUE
        year = document.document_publication_date[:4]
        month = document.document_publication_date[4:6]
        day = document.document_publication_date[6:]
        doc_to_publish.add_publication_date(year, month, day)

        doc_to_publish.add_in_issue(
            document.order,
            document.fpage,
            document.fpage_seq,
            document.lpage,
            document.elocation,
        )

        # ISSUE
        bundle_id = get_bundle_id(
            document.journal,
            document.year,
            document.volume,
            document.number,
            document.supplement,
        )
        doc_to_publish.add_issue(bundle_id)

        # JOURNAL
        doc_to_publish.add_journal(document.journal)

        # IDIOMAS
        for item in document.doi_with_lang:
            doc_to_publish.add_doi_with_lang(item["language"], item["doi"])

        for item in document.abstracts:
            doc_to_publish.add_abstract(item['language'], item['text'])

        for item in document.translated_sections:
            doc_to_publish.add_section(item['language'], item['text'])

        for item in document.translated_titles:
            doc_to_publish.add_translated_titles(
                item['language'], item['text'],
            )
        for lang, keywords in document.keywords_groups.items():
            doc_to_publish.add_keywords(lang, keywords)

        # ARQUIVOS
        # xml
        doc_to_publish.add_xml(document_files_migration.xmls[0].uri)

        # htmls
        for item in document_files_migration.text_langs:
            doc_to_publish.add_html(item['lang'], uri=None)

        # pdfs
        for item in document_files_migration.pdfs:
            doc_to_publish.add_pdf(
                lang=item.lang,
                url=item.uri,
                filename=item.name,
                type='pdf',
            )

        # mat supl
        for item in document_files_migration.suppl_mats:
            doc_to_publish.add_mat_suppl(
                lang=None, url=item.uri, ref_id=None, filename=item.name)

        # RELATED
        # doc_to_publish.add_related_article(doi, ref_id, related_type)
        # <related-article
        #  ext-link-type="doi" id="A01"
        #  related-article-type="commentary-article"
        #  xlink:href="10.1590/0101-3173.2022.v45n1.p139">

        for item in document_files_migration.related_items:
            doc_to_publish.add_related_article(
                doi=item['href'],
                ref_id=item['id'],
                related_type=item["related-article-type"],
            )

        doc_to_publish.publish_document()
    except Exception as e:
        raise exceptions.PublishDocumentError(
            _("Unable to publish {} {}").format(pid, e)
        )

    try:
        document_migration.status = MS_PUBLISHED
        document_migration.save()
    except Exception as e:
        raise exceptions.PublishDocumentError(
            _("Unable to upate document_migration status {} {}").format(
                pid, e
            )
        )


class DocumentFilesController:

    def __init__(self,
                 files_storage,
                 issue_files_migration,
                 file_id,
                 ):
        self.files_storage = files_storage
        self.issue_files_migration = issue_files_migration
        self._file_id = file_id

    @property
    def xml_files(self):
        if not hasattr(self, '_xml_files') and not self._xml_files:
            self._xml_files = self.issue_files_migration.xmls.filter(
                file_id=self._file_id)
        return self._xml_files

    @property
    def pdf_files(self):
        if not hasattr(self, '_pdf_files') and self._pdf_files:
            self._pdf_files = self.issue_files_migration.pdfs.filter(
                file_id=self._file_id)
        return self._pdf_files

    @property
    def html_files(self):
        if not hasattr(self, '_html_files') and not self._html_files:
            self._html_files = self.issue_files_migration.htmls.filter(
                file_id=self._file_id)
        return self._html_files

    @property
    def asset_files(self):
        if not hasattr(self, '_asset_files') and not self._asset_files:
            self._asset_files = self.issue_files_migration.assets.filter(
                file_id=self._file_id)
        return self._asset_files

    @property
    def assets(self):
        if not hasattr(self, '_assets') and not self._assets:
            self._assets = {
                asset.name: asset
                for asset in self.asset_files
            }
        return self._assets

    @property
    def text_langs(self):
        if not hasattr(self, '_text_langs') and not self._text_langs:
            if self.xmltree:
                self._text_langs = [
                    {"lang": rendition.language}
                    for rendition in ArticleRenditions(self.xmltree).article_renditions
                ]
            else:
                self._text_langs = [
                    {"lang": rendition.language}
                    for rendition in self.html_files
                    if rendition.part == "front"
                ]
        return self._text_langs

    @property
    def related_items(self):
        if not hasattr(self, '_related_items') and not self._related_items:
            items = []
            for xml_file in self.xml_files:
                related = RelatedItems(self.xmltree[self._file_id])
                items.extend(list(related.related_articles))
            self._related_items = items
        return self._related_items

    def get_object_name(self, file_path):
        return self.files_storage.build_object_name(
            file_path, self._publication_subdir, preserve_name=True
        )

    @property
    def xmltree(self):
        if not hasattr(self, '_xmltree') or not self._xmltree:
            self._xmltree = {}
            for item in self.xml_files:
                self._xmltree[item.name] = read_xml_file(
                    self.files_storage.fget(item.object_name))
        return self._xmltree

    @property
    def suppl_mats(self):
        for xmltree in self.xmltree.values():
            _suppl_mats = SupplementaryMaterials(self.xmltree)
            if _suppl_mats.items:
                for item in _suppl_mats.items:
                    yield self.assets[item.name]

    @property
    def xmls(self):
        if self.xmltree:
            for xml_file in self.xml_files:
                article_assets = ArticleAssets(self.xmltree[xml_file.name])
                from_to = {k: v.uri for k, v in self.assets.items()}
                article_assets.replace_names(from_to)

                object_name = self.get_object_name(xml_file.name)
                uri = self.files_storage.fput_content(
                    tostring(article_assets.xmltree),
                    mimetype="text/xml",
                    object_name=object_name
                )

                yield SciELOFile(**{
                    "name": xml_file.name, "uri": uri,
                    "object_name": object_name, "file_id": xml_file.file_id})

    @property
    def htmls(self):
        if self.html_files:
            yield from self.html_files

    @property
    def pdfs(self):
        if self.pdf_files:
            yield from self.pdf_files

    @property
    def assets(self):
        if self.asset_files:
            yield from self.asset_files
