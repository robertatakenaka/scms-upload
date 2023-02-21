import logging
import json
import os
import logging
import traceback
import sys
from datetime import datetime
from random import randint
from io import StringIO
from tempfile import TemporaryDirectory

from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model
from django.db.models import Q
from django_celery_beat.models import PeriodicTask, CrontabSchedule
from scielo_classic_website import classic_ws

from publication.db import mk_connection
from core.controller import parse_yyyymmdd, insert_hyphen_in_YYYYMMMDD
from core.controller import parse_non_standard_date, parse_months_names
from collection.choices import CURRENT
from collection.models import (
    ClassicWebsiteConfiguration,
    NewWebSiteConfiguration,
)
from files_storage.models import MinioConfiguration
from files_storage.controller import FilesStorageManager
from .models import (
    MigratedJournal,
    MigratedIssue,
    MigratedDocument,
    MigrationFailure,
    MigrationConfiguration,
)
from .choices import MS_IMPORTED, MS_PUBLISHED, MS_TO_IGNORE
from . import exceptions
from journal.models import OfficialJournal
from issue.models import Issue
from pid_provider.controller import ArticleXMLRegistration


User = get_user_model()


def start(user):
    try:
        migration_configuration = MigrationConfiguration.get_or_create(
            ClassicWebsiteConfiguration.objects.all().first(),
            NewWebSiteConfiguration.objects.all().first(),
            MinioConfiguration.get_or_create(name='website'),
            MinioConfiguration.get_or_create(name='migration'),
            user,
        )

        schedule_journals_and_issues_migrations(
            migration_configuration.classic_website_config.collection.acron,
            user,
        )

    except Exception as e:
        logging.exception(e)
        raise exceptions.MigrationStartError(
            "Unable to start migration %s" % e)


def schedule_journals_and_issues_migrations(collection_acron, user):
    """
    Agenda tarefas para importar e publicar dados de title e issue
    """
    logging.info(_("Schedule journals and issues migrations tasks"))
    items = (
        ("title", _("Migrate journals"), 'migration', 0, 2, 0),
        ("issue", _("Migrate issues"), 'migration', 0, 7, 2),
    )

    for db_name, task, action, hours_after_now, minutes_after_now, priority in items:
        for mode in ("full", "incremental"):
            name = f'{collection_acron} | {db_name} | {action} | {mode}'
            kwargs = dict(
                collection_acron=collection_acron,
                user_id=user.id,
                force_update=(mode == "full"),
            )
            try:
                periodic_task = PeriodicTask.objects.get(name=name)
            except PeriodicTask.DoesNotExist:
                hours, minutes = sum_hours_and_minutes(
                    hours_after_now, minutes_after_now)

                periodic_task = PeriodicTask()
                periodic_task.name = name
                periodic_task.task = task
                periodic_task.kwargs = json.dumps(kwargs)
                if mode == "full":
                    periodic_task.priority = priority
                    periodic_task.enabled = False
                    periodic_task.one_off = True
                    periodic_task.crontab = get_or_create_crontab_schedule(
                        hour=hours,
                        minute=minutes,
                    )
                else:
                    periodic_task.priority = priority
                    periodic_task.enabled = True
                    periodic_task.one_off = False
                    periodic_task.crontab = get_or_create_crontab_schedule(
                        minute=minutes,
                    )
                periodic_task.save()
    logging.info(_("Scheduled journals and issues migrations tasks"))


def schedule_issue_documents_migration(collection_acron,
                                       journal_acron,
                                       scielo_issn,
                                       publication_year,
                                       user):
    """
    Agenda tarefas para migrar e publicar um conjunto de documentos por:
        - ano
        - periódico
        - periódico e ano
    """
    logging.info(_("Schedule issue documents migration {} {} {} {}").format(
        collection_acron,
        journal_acron,
        scielo_issn,
        publication_year,
    ))
    action = 'migrate'
    task = _('Migrate documents')

    params_list = (
        {"scielo_issn": scielo_issn, "publication_year": publication_year},
        {"scielo_issn": scielo_issn},
        {"publication_year": publication_year},
    )
    documents_group_ids = (
        f"{journal_acron} {publication_year}",
        f"{journal_acron}",
        f"{publication_year}",
    )

    count = 0
    for group_id, params in zip(documents_group_ids, params_list):
        count += 1
        if len(params) == 2:
            modes = ("full", "incremental")
        else:
            modes = ("incremental", )

        for mode in modes:

            name = f'{collection_acron} | {group_id} | {action} | {mode}'

            kwargs = dict(
                collection_acron=collection_acron,
                user_id=user.id,
                force_update=(mode == "full"),
            )
            kwargs.update(params)

            try:
                periodic_task = PeriodicTask.objects.get(name=name, task=task)
            except PeriodicTask.DoesNotExist:
                now = datetime.utcnow()
                periodic_task = PeriodicTask()
                periodic_task.name = name
                periodic_task.task = task
                periodic_task.kwargs = json.dumps(kwargs)
                if mode == "full":
                    # full: force_update = True
                    # modo full está programado para ser executado manualmente
                    # ou seja, a task fica disponível para que o usuário
                    # apenas clique em RUN e rodará na sequência,
                    # não dependente dos atributos: enabled, one_off, crontab

                    # prioridade alta
                    periodic_task.priority = 1
                    # desabilitado para rodar automaticamente
                    periodic_task.enabled = False
                    # este parâmetro não é relevante devido à execução manual
                    periodic_task.one_off = True
                    # este parâmetro não é relevante devido à execução manual
                    hours, minutes = sum_hours_and_minutes(0, 1)
                    periodic_task.crontab = get_or_create_crontab_schedule(
                        hour=hours,
                        minute=minutes,
                    )
                else:
                    # modo incremental está programado para ser executado
                    # automaticamente
                    # incremental: force_update = False

                    # prioridade 3, exceto se houver ano de publicação
                    periodic_task.priority = 3
                    if publication_year:
                        # estabelecer prioridade maior para os mais recentes
                        periodic_task.priority = (
                            datetime.now().year - int(publication_year)
                        )

                    # deixa habilitado para rodar frequentemente
                    periodic_task.enabled = True

                    # programado para rodar automaticamente 1 vez se o ano de
                    # publicação não é o atual
                    periodic_task.one_off = (
                        publication_year and
                        publication_year != datetime.now().year
                    )

                    # distribui as tarefas para executarem dentro de 1h
                    # e elas executarão a cada 1h
                    hours, minutes = sum_hours_and_minutes(0, count % 100)
                    periodic_task.crontab = get_or_create_crontab_schedule(
                        # hour=hours,
                        minute=minutes,
                    )
                periodic_task.save()
    logging.info(_("Scheduled {} tasks to migrate documents").format(count))


def sum_hours_and_minutes(hours_after_now, minutes_after_now, now=None):
    """
    Retorna a soma dos minutos / horas a partir da hora atual
    """
    now = now or datetime.utcnow()
    hours = now.hour + hours_after_now
    minutes = now.minute + minutes_after_now
    if minutes > 59:
        hours += 1
    hours = hours % 24
    minutes = minutes % 60
    return hours, minutes


def get_or_create_crontab_schedule(day_of_week=None, hour=None, minute=None):
    try:
        crontab_schedule, status = CrontabSchedule.objects.get_or_create(
            day_of_week=day_of_week or '*',
            hour=hour or '*',
            minute=minute or '*',
        )
    except Exception as e:
        logging.exception(e)
        raise exceptions.GetOrCreateCrontabScheduleError(
            _('Unable to get_or_create_crontab_schedule {} {} {} {} {}').format(
                day_of_week, hour, minute, type(e), e
            )
        )
    return crontab_schedule


class MigrationConfigurationController:

    def __init__(self, collection_acron, user):
        self.config = (
            MigrationConfiguration.objects.get(
                classic_website_config__collection__acron=collection_acron)
        )
        classic_website_config = self.config.classic_website_config
        self.classic_website = classic_ws.ClassicWebsite(
            bases_path=classic_website_config.bases_path,
            bases_work_path=classic_website_config.bases_work_path,
            bases_translation_path=classic_website_config.bases_translation_path,
            bases_pdf_path=classic_website_config.bases_pdf_path,
            bases_xml_path=classic_website_config.bases_xml_path,
            htdocs_img_revistas_path=classic_website_config.htdocs_img_revistas_path,
            serial_path=classic_website_config.serial_path,
            cisis_path=classic_website_config.cisis_path,
            title_path=classic_website_config.title_path,
            issue_path=classic_website_config.issue_path,
        )
        self.fs_managers = dict(
            website=FilesStorageManager(
                self.config.public_files_storage_config.name),
            migration=FilesStorageManager(
                self.config.migration_files_storage_config.name),
        )
        self.user = user

    @property
    def article_ids_provider(self):
        return ArticleXMLRegistration()

    def connect_db(self):
        try:
            return mk_connection(self.config.new_website_config.db_uri)
        except Exception as e:
            logging.exception(e)
            raise exceptions.GetMigrationConfigurationError(
                _("Unable to connect db {} {}").format(type(e), e)
            )

    def get_journals_pids_and_records(self):
        return self.classic_website.get_journals_pids_and_records()

    def get_issues_pids_and_records(self):
        return self.classic_website.get_issues_pids_and_records()

    def get_documents_pids_and_records(self, journal_acron, issue_folder, issue_pid):
        """
        obtém registros da base "artigo" que não necessariamente é só
        do fascículo de migrated_issue
        possivelmente source_file pode conter registros de outros fascículos
        se source_file for acrônimo
        """
        logging.info(
            f"Importing documents records {journal_acron} {issue_folder}")
        issue = {"issue_pid": issue_pid, }
        for grp_id, grp_records in self.classic_website.get_documents_pids_and_records(
                journal_acron, issue_folder, issue_pid):

            if len(grp_records) == 1:
                # é possível que em source_file_path exista registro tipo i
                issue = {"issue_pid": grp_id, "issue_records": grp_records}
                continue

            data = {"pid": grp_id, "records": grp_records}
            data.update(issue)
            issue = {}
            yield data

    def get_classic_website_issue_files(self, journal_acron, issue_folder):
        return self.classic_website.get_issue_files(
            journal_acron, issue_folder)

    def get_files_storage(self, filename):
        name, ext = os.path.splitext(filename)
        if ext in (".xml", ".html", ".htm"):
            return self.fs_managers['migration']
        else:
            return self.fs_managers['website']


def migrate_journals(
        user,
        collection_acron,
        force_update=False,
        ):
    mcc = MigrationConfigurationController(collection_acron, user)
    for scielo_issn, journal_data in mcc.get_journals_pids_and_records():
        journal_migration = JournalMigration(
            user, collection_acron, scielo_issn,
            journal_data[0], force_update)
        journal_migration.import_data_from_title_database()


def migrate_issues(
        user,
        collection_acron,
        force_update=False,
        ):
    mcc = MigrationConfigurationController(collection_acron, user)
    # mcc.connect_db()
    for issue_pid, issue_data in mcc.get_issues_pids_and_records():
        issue_migration = IssueMigration(
            user=user,
            collection_acron=collection_acron,
            scielo_issn=issue_pid[:9],
            issue_pid=issue_pid,
            issue_data=issue_data[0],
            force_update=force_update,
        )
        issue_migration.import_data_from_issue_database()
        issue_migration.schedule_issue_documents_migration()


def import_issues_files_and_migrate_documents(
        user,
        collection_acron,
        scielo_issn=None,
        publication_year=None,
        force_update=False,
        ):

    docs_migration = DocumentsMigration(
        collection_acron, scielo_issn, publication_year, force_update, user)

    for migrated_issue in docs_migration.choose_issues():
        docs_migration.migrate_documents(migrated_issue)


class JournalMigration:

    def __init__(self, user, collection_acron,
                 scielo_issn,
                 journal_data, force_update=False):
        self.user = user
        self.collection_acron = collection_acron
        self.scielo_issn = scielo_issn
        self.journal_data = journal_data
        self.force_update = force_update

    @property
    def classic_website_journal(self):
        if not hasattr(self, '_journal') or not self._journal:
            self._journal = classic_ws.Journal(self.journal_data)
        return self._journal

    @property
    def official_journal(self):
        if not hasattr(self, '_official_journal') or not self._official_journal:
            self._official_journal = OfficialJournal.get_or_create(
                title=self.classic_website_journal.title,
                issn_l=None,
                e_issn=self.classic_website_journal.electronic_issn,
                print_issn=self.classic_website_journal.print_issn,
                creator=self.user,
            )
            year, month, day = parse_yyyymmdd(self.classic_website_journal.first_year)
            self._official_journal.update(
                self.user,
                short_title=self.classic_website_journal.title_iso,
                foundation_date=self.classic_website_journal.first_year,
                foundation_year=year,
                foundation_month=month,
                foundation_day=day,
            )
        return self._official_journal

    def import_data_from_title_database(self):
        migrated_journal = MigratedJournal.get_or_create(
            self.collection_acron, self.scielo_issn, self.user)
        migrated_journal.update(
            self.user,
            self.classic_website_journal, self.force_update,
            journal_data=self.journal_data,
            acron=self.classic_website_journal.acronym,
            title=self.classic_website_journal.title,
            availability_status=self.classic_website_journal.current_status,
            official_journal=self.official_journal,
        )
        return migrated_journal


class IssueMigration:

    def __init__(self, user,
                 collection_acron,
                 scielo_issn,
                 issue_pid,
                 issue_data,
                 force_update,
                 ):
        self.user = user
        self.collection_acron = collection_acron
        self.scielo_issn = scielo_issn
        self.issue_pid = issue_pid
        self.force_update = force_update
        self.issue_data = issue_data

    @property
    def classic_website_issue(self):
        if not hasattr(self, '_classic_website_issue') or not self._classic_website_issue:
            self._classic_website_issue = classic_ws.Issue(self.issue_data)
        return self._classic_website_issue

    @property
    def migrated_issue(self):
        if not hasattr(self, '_migrated_issue') or not self._migrated_issue:
            self._migrated_issue = MigratedIssue.get_or_create(
                migrated_journal=MigratedJournal.get_or_create(
                    collection_acron=self.collection_acron,
                    scielo_issn=self.scielo_issn),
                issue_pid=self.issue_pid,
                issue_folder=self.classic_website_issue.issue_label,
                creator=self.user)
        return self._migrated_issue

    def import_data_from_issue_database(self):
        try:
            logging.info("Import data from database issue {} {} {}".format(
                self.collection_acron, self.scielo_issn, self.issue_pid))

            self.migrated_issue.add_data(
                self.classic_website_issue,
                self.official_issue,
                self.issue_data,
                self.force_update,
            )
            logging.info(self.migrated_issue.status)
            return self.migrated_issue
        except Exception as e:
            logging.exception(e)
            logging.error(_("Error importing issue {} {} {}").format(
                collection_acron, issue_pid, issue_data))
            logging.exception(e)
            raise exceptions.IssueMigrationSaveError(
                _("Unable to save {} migration {} {} {}").format(
                    "issue", collection_acron, issue_pid, e
                )
            )

    def schedule_issue_documents_migration(self):
        if self.migrated_issue.status == MS_IMPORTED:
            schedule_issue_documents_migration(
                collection_acron=self.collection_acron,
                journal_acron=self.migrated_issue.migrated_journal.acron,
                scielo_issn=self.migrated_issue.migrated_journal.scielo_issn,
                publication_year=self.migrated_issue.official_issue.publication_year,
                user=self.user,
            )

    def _get_months_from_issue(self):
        """
        Get months from issue (classic_website.Issue)
        """
        months_names = {}
        for item in self.classic_website_issue.bibliographic_strip_months:
            if item.get("text"):
                months_names[item['lang']] = item.get("text")
        if months_names:
            return months_names.get("en") or months_names.values()[0]

    @property
    def official_journal(self):
        if not hasattr(self, '_official_journal') or not self._official_journal:
            self._official_journal = MigratedJournal.get_or_create(
                    collection_acron=self.collection_acron,
                    scielo_issn=self.scielo_issn).official_journal
        return self._official_journal

    @property
    def official_issue(self):
        if self.classic_website_issue.is_press_release:
            # press release não é um documento oficial,
            # sendo assim, não será criado official issue correspondente
            self._official_issue = None
            return self._official_issue

        if not hasattr(self, '_official_issue') or not self._official_issue:
            # obtém ou cria official_issue
            logging.info(_("Create official issue {}").format(
                self.classic_website_issue))

            flexible_date = parse_non_standard_date(
                self.classic_website_issue.publication_date)
            months = parse_months_names(self._get_months_from_issue())

            self._official_issue = Issue.get_or_create(
                self.official_journal,
                self.classic_website_issue.publication_year,
                self.classic_website_issue.volume,
                self.classic_website_issue.number,
                self.classic_website_issue.supplement,
                self.user,
                initial_month_number=flexible_date.get("month_number"),
                initial_month_name=months.get("initial_month_name"),
                final_month_name=months.get("final_month_name"),
            )
        return self._official_issue


class DocumentsMigration:

    def __init__(self, collection_acron, scielo_issn, publication_year, force_update, user):
        self.collection_acron = collection_acron
        self.scielo_issn = scielo_issn
        self.publication_year = publication_year
        self.force_update = force_update
        self.user = user
        self.mcc = MigrationConfigurationController(collection_acron, user)
        self.article_ids_provider = self.mcc.article_ids_provider

    def choose_issues(self):
        params = {
            'migrated_journal__collection__acron': self.collection_acron
        }
        if self.scielo_issn:
            params['migrated_journal__scielo_issn'] = self.scielo_issn
        if self.publication_year:
            params['official_issue__publication_year'] = self.publication_year
        return MigratedIssue.objects.filter(
            Q(status=MS_PUBLISHED) | Q(status=MS_IMPORTED),
            **params,
        ).iterator()

    def migrate_documents(self, default_migrated_issue):
        # get_documents_pids_and_records obtém registros de artigo
        # de serial, bases-work etc, assim sendo pode retornar artigos
        # de mais de um fascículo
        migrated_issue = default_migrated_issue
        journal_acron = migrated_issue.migrated_journal.acron
        issue_folder = migrated_issue.issue_folder
        issue_pid = migrated_issue.issue_pid

        for item in self.mcc.get_documents_pids_and_records(
                journal_acron, issue_folder, issue_pid):
            issue_pid = item.get("issue_pid")
            if issue_pid and issue_pid != default_migrated_issue.issue_pid:
                migrated_issue = MigratedIssue.objects.get(
                    migrated_journal__collection__acron=self.collection_acron,
                    issue_pid=issue_pid,
                )

            self.import_issue_files(migrated_issue)
            journal_issue_and_document_data = {
                'title': migrated_issue.migrated_journal.data,
                'issue': migrated_issue.data,
                'article': item['records'],
            }
            migrated_document = self.migrate_document(
                migrated_issue, item['pid'], journal_issue_and_document_data)
            self.request_pids(migrated_document)

    def import_issue_files(self, migrated_issue):
        logging.info(f"Import issue files {migrated_issue}")
        if migrated_issue.files_status == MS_IMPORTED and not self.force_update:
            logging.info("Skip")
            return
        classic_issue_files = self.mcc.get_classic_website_issue_files(
            migrated_issue.migrated_journal.acron,
            migrated_issue.issue_folder,
        )
        migrated_issue.add_files(
            classic_issue_files=classic_issue_files,
            get_files_storage=self.mcc.get_files_storage,
            creator=self.user,
        )
        migrated_issue.save()

    def migrate_document(self, migrated_issue, article_pid,
                         journal_issue_and_document_data):
        issue_pid = migrated_issue.issue_pid
        document = classic_ws.Document(journal_issue_and_document_data)

        # instancia Document com registros de title, issue e artigo
        pid = document.scielo_pid_v2 or article_pid

        if document.scielo_pid_v2 != pid:
            document.scielo_pid_v2 = pid

        migrated_document = MigratedDocument.get_or_create(
            pid=pid,
            pkg_name=document.filename_without_extension,
            migrated_issue=migrated_issue,
            aop_pid=document.aop_pid,
            v3=document.scielo_pid_v3,
            creator=self.user,
        )
        migrated_document.add_data(
            document,
            journal_issue_and_document_data,
            self.force_update,
            self.user,
        )
        migrated_document.add_pdfs(self.force_update)
        migrated_document.add_htmls(self.force_update)
        migrated_document.add_migrated_xmls(self.force_update)
        migrated_document.add_generated_xmls(
            document=document,
            migration_fs_manager=self.mcc.fs_managers['migration'],
            user=self.user,
            force_update=self.force_update,
        )
        return migrated_document

    def request_pids(self, migrated_document):
        # solicitar pid v3
        logging.debug("XML WITH PRE %s" % type(migrated_document.xml_with_pre))
        logging.info("migrated_document.xml_with_pre ids %s %s %s" %
            (
                migrated_document.xml_with_pre.v3,
                migrated_document.xml_with_pre.v2,
                migrated_document.xml_with_pre.aop_pid,
                ))
        # cria / atualiza artigo de app publication
        response = self.article_ids_provider.register(
            xml_with_pre=migrated_document.xml_with_pre,
            name=migrated_document.pkg_name + ".xml",
            user=self.user,
            # pdfs=migrated_document.rendition_files,
        )
        logging.info("response %s " % response)
        try:
            registered = response['registered']
            migrated_document.pid = registered.get("v2")
            migrated_document.v3 = registered.get("v3")
            migrated_document.aop_pid = registered.get("aop_pid")
            migrated_document.save()
        except KeyError:
            # TODO o que fazer quando response['error']
            logging.exception(response)
        else:
            migrated_document.finish(self.user)
