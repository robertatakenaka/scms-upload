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
from lxml import etree
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
from scielo_classic_website import classic_ws

from core.controller import parse_yyyymmdd, insert_hyphen_in_YYYYMMMDD
from libs.dsm.publication.db import mk_connection
from libs.dsm.publication.journals import JournalToPublish
from libs.dsm.publication.issues import IssueToPublish, get_bundle_id
from core.controller import parse_non_standard_date, parse_months_names
from collection.choices import CURRENT
from collection.exceptions import (
    GetSciELOJournalError,
)
from collection.models import (
    ClassicWebsiteConfiguration,
    NewWebSiteConfiguration,
)
from files_storage.models import Configuration as FilesStorageConfiguration
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
from publication.models import PublicationArticle
from publication.choices import PUBLICATION_STATUS_PUBLISHED


User = get_user_model()


def read_xml_file(file_path):
    return etree.parse(file_path)


def _get_classic_website_rel_path(file_path):
    if 'htdocs' in file_path:
        return file_path[file_path.find("htdocs"):]
    if 'base' in file_path:
        return file_path[file_path.find("base"):]


def start(user):
    try:
        migration_configuration = MigrationConfiguration.get_or_create(
            ClassicWebsiteConfiguration.objects.all().first(),
            NewWebSiteConfiguration.objects.all().first(),
            FilesStorageConfiguration.get_or_create(name='website'),
            FilesStorageConfiguration.get_or_create(name='migration'),
            user,
        )

        schedule_journals_and_issues_migrations(
            migration_configuration.classic_website_config.collection.acron,
            user,
        )

    except Exception as e:
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


def schedule_issues_documents_migration(collection_acron, user):
    """
    Agenda tarefas para migrar e publicar todos os documentos
    """
    for migrated_issue in MigratedIssue.objects.filter(
            migrated_journal__collection__acron=collection_acron):

        journal_acron = migrated_issue.migrated_journal.acron
        scielo_issn = migrated_issue.migrated_journal.scielo_issn
        publication_year = migrated_issue.official_issue.publication_year

        schedule_issue_documents_migration(
            collection_acron, journal_acron,
            scielo_issn, publication_year, user)


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
        self.classic_website = self.config.classic_website_config
        self.fs_managers = dict(
            website=FilesStorageManager(
                self.config.public_files_storage_config.name),
            migration=FilesStorageManager(
                self.config.migration_files_storage_config.name),
        )
        self.user = user

    def connect_db(self):
        try:
            return mk_connection(self.config.new_website_config.db_uri)
        except Exception as e:
            raise exceptions.GetMigrationConfigurationError(
                _("Unable to connect db {} {}").format(type(e), e)
            )

    def get_source_file_path(self, db_name):
        try:
            return getattr(self.classic_website, f'{db_name}_path')
        except AttributeError:
            raise exceptions.GetMigrationConfigurationError(
                _("Unable to get path of {} {} {}").format(
                    db_name, type(e), e)
            )

    def get_artigo_source_files_paths(self, journal_acron, issue_folder):
        """
        Apesar de fornecer `issue_folder` o retorno pode ser a base de dados
        inteira do `journal_acron`
        """
        logging.info("Harvest classic website records {} {}".format(journal_acron, issue_folder))
        try:
            artigo_source_files_paths = classic_ws.get_artigo_db_path(
                journal_acron, issue_folder, self.classic_website)
        except Exception as e:
            raise exceptions.IssueFilesStoreError(
                _("Unable to get artigo db paths from classic website {} {} {}").format(
                    journal_acron, issue_folder, e,
                )
            )
        logging.info(artigo_source_files_paths)
        return artigo_source_files_paths

    def get_classic_website_issue_files(self, journal_acron, issue_folder):
        try:
            classic_website_paths = {
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
        try:
            issue_files = classic_ws.get_issue_files(
                journal_acron, issue_folder, classic_website_paths)
        except Exception as e:
            raise exceptions.IssueFilesStoreError(
                _("Unable to get issue files from classic website {} {} {}").format(
                    journal_acron, issue_folder, e,
                )
            )

        for info in issue_files:
            try:
                info['relative_path'] = _get_classic_website_rel_path(info['path'])
            except Exception as e:
                info['error'] = str(e)
                info['error_type'] = str(type(e))
            yield info

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
    try:
        action = "migrate"
        mcc = MigrationConfigurationController(collection_acron, user)
        # mcc.connect_db()
        source_file_path = mcc.get_source_file_path("title")

        for scielo_issn, journal_data in classic_ws.get_records_by_source_path(
                "title", source_file_path):
            migrated_journal = import_data_from_title_database(
                user, collection_acron,
                scielo_issn, journal_data[0], force_update)
    except Exception as e:
        raise exceptions.JournalMigrationError(
            _("Unable to migrate journals {}").format(collection_acron)
        )


def import_data_from_title_database(user, collection_acron,
                                    scielo_issn,
                                    journal_data, force_update=False):
    """
    Create/update JournalMigration
    """
    try:
        # obtém classic website journal
        classic_website_journal = classic_ws.Journal(journal_data)

        year, month, day = parse_yyyymmdd(classic_website_journal.first_year)
        logging.info((year, month, day))
        # cria ou obtém official_journal
        official_journal = OfficialJournal.get_or_create(
            title=classic_website_journal.title,
            issn_l=None,
            e_issn=classic_website_journal.electronic_issn,
            print_issn=classic_website_journal.print_issn,
            creator=user,
        )
        logging.info(official_journal)
        official_journal.update(
            user,
            short_title=classic_website_journal.title_iso,
            foundation_date=classic_website_journal.first_year,
            foundation_year=year,
            foundation_month=month,
            foundation_day=day,
        )
        migrated_journal = MigratedJournal.get_or_create(
            collection_acron, scielo_issn, user)
        migrated_journal.update(
            user,
            classic_website_journal, force_update,
            journal_data=journal_data,
            acron=classic_website_journal.acronym,
            title=classic_website_journal.title,
            availability_status=classic_website_journal.current_status,
            official_journal=official_journal,
        )
        return migrated_journal
    except Exception as e:
        migrated_journal.failures.add(
            MigrationFailure.create(
                _("Unable to migrate journal {} {}").format(
                    collection_acron, scielo_issn),
                action, e, user))
        migrated_journal.save()


def publish_imported_journal(migrated_journal):
    journal = classic_ws.Journal(migrated_journal.data)
    if journal.current_status != CURRENT:
        # journal must not be published
        return

    if migrated_journal.status != MS_IMPORTED:
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
        #         previous_journal = get_migrated_journal_by_title(
        #             journal.previous_title)
        #     except GetSciELOJournalError:
        #         previous_journal = None
        # if journal.next_title:
        #     try:
        #         next_journal = get_migrated_journal_by_title(journal.next_title)
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
                migrated_journal, type(e), e)
        )

    try:
        migrated_journal.status = MS_PUBLISHED
        migrated_journal.save()
    except Exception as e:
        raise exceptions.PublishJournalError(
            _("Unable to publish {} {} {}").format(
                migrated_journal, type(e), e)
        )


def migrate_issues(
        user,
        collection_acron,
        force_update=False,
        ):
    mcc = MigrationConfigurationController(collection_acron, user)
    # mcc.connect_db()
    source_file_path = mcc.get_source_file_path("issue")

    for issue_pid, issue_data in classic_ws.get_records_by_source_path("issue", source_file_path):
        try:
            action = "import"
            migrated_issue = import_data_from_issue_database(
                user=user,
                collection_acron=collection_acron,
                scielo_issn=issue_pid[:9],
                issue_pid=issue_pid,
                issue_data=issue_data[0],
                force_update=force_update,
            )
            if migrated_issue.status == MS_IMPORTED:
                schedule_issue_documents_migration(
                    collection_acron=collection_acron,
                    journal_acron=migrated_issue.migrated_journal.acron,
                    scielo_issn=migrated_issue.migrated_journal.scielo_issn,
                    publication_year=migrated_issue.official_issue.publication_year,
                    user=user,
                )
                # publish_imported_issue(migrated_issue)
        except Exception as e:
            migrated_issue.failures.add(
                MigrationFailure.create(
                    _("Error migrating issue {} {}").format(collection_acron, issue_pid),
                    action, e, user))
            migrated_issue.save()


def import_data_from_issue_database(
        user,
        collection_acron,
        scielo_issn,
        issue_pid,
        issue_data,
        force_update=False,
        ):
    """
    Create/update IssueMigration
    """
    try:
        logging.info("Import data from database issue {} {} {}".format(
            collection_acron, scielo_issn, issue_pid))

        classic_website_issue = classic_ws.Issue(issue_data)

        migrated_issue = MigratedIssue.get_or_create(
            migrated_journal=MigratedJournal.get_or_create(
                collection_acron=collection_acron,
                scielo_issn=scielo_issn),
            issue_pid=issue_pid,
            issue_folder=classic_website_issue.issue_label,
            creator=user)
        official_issue = create_official_issue(
            classic_website_issue, collection_acron,
            scielo_issn, issue_pid, user
        )
        migrated_issue.update(
            classic_website_issue, official_issue, issue_data, force_update
        )
        return migrated_issue
    except Exception as e:
        logging.error(_("Error importing issue {} {} {}").format(
            collection_acron, issue_pid, issue_data))
        logging.exception(e)
        raise exceptions.IssueMigrationSaveError(
            _("Unable to save {} migration {} {} {}").format(
                "issue", collection_acron, issue_pid, e
            )
        )


def _get_months_from_issue(classic_website_issue):
    """
    Get months from issue (classic_website.Issue)
    """
    months_names = {}
    for item in classic_website_issue.bibliographic_strip_months:
        if item.get("text"):
            months_names[item['lang']] = item.get("text")
    if months_names:
        return months_names.get("en") or months_names.values()[0]


def create_official_issue(classic_website_issue, collection_acron,
                          scielo_issn, issue_pid,
                          user):
    if classic_website_issue.is_press_release:
        # press release não é um documento oficial,
        # sendo assim, não será criado official issue correspondente
        return

    try:
        # obtém ou cria official_issue
        logging.info(_("Create official issue {}").format(
            classic_website_issue))

        flexible_date = parse_non_standard_date(
            classic_website_issue.publication_date)
        months = parse_months_names(_get_months_from_issue(
            classic_website_issue))
        official_journal = MigratedJournal.get_or_create(
            collection_acron=collection_acron,
            scielo_issn=scielo_issn).official_journal
        return Issue.get_or_create(
            official_journal,
            classic_website_issue.publication_year,
            classic_website_issue.volume,
            classic_website_issue.number,
            classic_website_issue.supplement,
            user,
            initial_month_number=flexible_date.get("month_number"),
            initial_month_name=months.get("initial_month_name"),
            final_month_name=months.get("final_month_name"),
        )
    except Exception as e:
        raise exceptions.GetOrCreateOfficialIssueError(
            _("Unable to set official issue to SciELO issue {} {} {}").format(
                classic_website_issue, type(e), e
            )
        )


def publish_imported_issue(migrated_issue):
    """
    Raises
    ------
    PublishIssueError
    """
    issue = classic_ws.Issue(migrated_issue.data)

    if migrated_issue.status != MS_IMPORTED:
        logging.info("Skipped: publish issue {}".format(migrated_issue))
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
        # para uso de indicação fascículo aop "desativado"
        issue_to_publish.has_docs = []

        issue_to_publish.publish_issue()
    except Exception as e:
        raise exceptions.PublishIssueError(
            _("Unable to publish {} {}").format(
                migrated_issue.issue_pid, e)
        )

    try:
        migrated_issue.status = MS_PUBLISHED
        migrated_issue.save()
    except Exception as e:
        raise exceptions.PublishIssueError(
            _("Unable to upate migrated_issue status {} {}").format(
                migrated_issue.issue_pid, e)
        )


def import_issues_files_and_migrate_documents(
        user,
        collection_acron,
        scielo_issn=None,
        publication_year=None,
        force_update=False,
        ):

    params = {
        'migrated_issue__migrated_journal__collection__acron': collection_acron
    }
    if scielo_issn:
        params['migrated_issue__migrated_journal__scielo_issn'] = scielo_issn
    if publication_year:
        params['migrated_issue__official_issue__publication_year'] = publication_year

    logging.info(params)

    items = IssueMigration.objects.filter(
        Q(status=MS_PUBLISHED) | Q(status=MS_IMPORTED),
        **params,
    )

    mcc = MigrationConfigurationController(collection_acron, user)
    # mcc.connect_db()

    # Melhor importar todos os arquivos e depois tratar da carga
    # dos metadados, e geração de XML, pois
    # há casos que os HTML mencionam arquivos de pastas diferentes
    # da sua pasta do fascículo
    for migrated_issue in items:
        import_issue_files(
            migrated_issue=migrated_issue,
            mcc=mcc,
            force_update=force_update,
        )

    for migrated_issue in items:
        try:
            for source_file_path in mcc.get_artigo_source_files_paths(
                    migrated_issue.migrated_journal.acron,
                    migrated_issue.issue_folder,
                    ):
                # migra os documentos da base de dados `source_file_path`
                # que não contém necessariamente os dados de só 1 fascículo
                migrate_documents(
                    mcc.user,
                    collection_acron,
                    source_file_path,
                    migrated_issue,
                    mcc,
                    force_update,
                )

        except Exception as e:
            migrated_issue.failures.add(
                MigrationFailure.create(
                    _("Error importing documents of {}").format(migrated_issue),
                    "import issue documents",
                    e,
                    user,
                )
            )
            migrated_issue.save()


# FIXME remover user_id
def import_issue_files(
        migrated_issue,
        mcc,
        force_update,
        ):
    """135
    Migra os arquivos do fascículo (pdf, img, xml ou html)
    """
    logging.info("Import issue files {}".format(migrated_issue))
    if migrated_issue.files_status == MS_IMPORTED and not force_update:
        logging.info("Skipped: Import files from classic website {}".format(
            migrated_issue))
        return

    try:
        classic_issue_files = mcc.get_classic_website_issue_files(
            migrated_issue.migrated_journal.acron,
            migrated_issue.issue_folder,
        )

        migrated_issue.add_files(
            classic_issue_files=classic_issue_files,
            get_files_storage=mcc.get_files_storage,
            creator=user,
        )
    except Exception as e:
        migrated_issue.failures.add(
            MigrationFailure.create(
                _("Error import isse files of {}").format(migrated_issue),
                "import issue files",
                e,
                user,
            )
        )
        migrated_issue.save()


def migrate_documents(
        user,
        collection_acron,
        source_file_path,
        migrated_issue,
        mcc,
        force_update=False,
        ):
    """
    Importa os registros presentes na base de dados `source_file_path`
    Importa os arquivos dos documentos (xml, pdf, html, imagens)
    Publica os artigos no site
    """
    try:
        # obtém os registros de title e issue
        journal_issue_and_document_data = {
            'title': migrated_issue.migrated_journal.data,
            'issue': migrated_issue.data,
        }

        # obtém registros da base "artigo" que não necessariamente é só
        # do fascículo de migrated_issue
        # possivelmente source_file pode conter registros de outros fascículos
        # se source_file for acrônimo
        logging.info("Importing documents records from source_file_path={}".format(source_file_path))
        for grp_id, grp_records in classic_ws.get_records_by_source_path(
                "artigo", source_file_path):
            try:
                logging.info(_("Get {} from {}").format(grp_id, source_file_path))
                if len(grp_records) == 1:
                    # é possível que em source_file_path exista registro tipo i
                    journal_issue_and_document_data['issue'] = grp_records[0]
                    continue

                journal_issue_and_document_data['article'] = grp_records
                document = classic_ws.Document(journal_issue_and_document_data)

                migrate_document(
                    mcc,
                    user,
                    collection_acron,
                    scielo_issn=document.journal.scielo_issn,
                    issue_pid=document.issue.pid,
                    document=document,
                    journal_issue_and_document_data=journal_issue_and_document_data,
                    force_update=force_update,
                )
            except Exception as e:
                migrated_issue.failures.add(
                    MigrationFailure.create(
                        _('Error migrating documents {}').format(migrated_issue),
                        'migrate issue documents',
                        e,
                        user,
                    )
                )
                migrated_issue.save()
    except Exception as e:
        migrated_issue.failures.add(
            MigrationFailure.create(
                _('Error migrating documents {}').format(migrated_issue),
                'migrate issue documents',
                e,
                user,
            )
        )
        migrated_issue.save()


def migrate_document(
        mcc,
        user,
        collection_acron,
        scielo_issn,
        issue_pid,
        document,
        journal_issue_and_document_data,
        force_update,
        ):
    try:
        # instancia Document com registros de title, issue e artigo
        pid = document.pid

        migrated_journal = MigratedJournal.get_or_create(
                collection_acron, scielo_issn, user)
        migrated_issue = MigratedIssue.get_or_create(
            migrated_journal, issue_pid, document.issue.issue_label, user)

        migrated_document = MigratedDocument.get_or_create(
            pid=pid,
            key=document.filename_without_extension,
            migrated_issue=migrated_issue,
            creator=user,
        )
        migrated_document.add_files(
            classic_website_document=document,
            original_language=document.original_language,
            migration_fs_manager=mcc.fs_managers['migration'],
            updated_by=user,
        )
        # solicitar pid v3
        # cria / atualiza artigo de app publication
        article = PublicationArticle.register(
            xml_with_pre=migrated_document.xml_with_pre,
            name=migrated_document.pkg_name + ".xml",
            user=user,
        )
        article.pdf_files.set(migrated_document.rendition_files)

        # atualiza status da migração
        migrated_document.add_data(
            document,
            journal_issue_and_document_data,
            force_update,
        )
    except Exception as e:
        migrated_document.failures.add(
            MigrationFailure.create(
                _("Unable to migrate document {} {} {}").format(
                    migrated_journal, migrated_issue, pid
                ),
                "document migration",
                e, user,
            )
        )
        migrated_document.save()
