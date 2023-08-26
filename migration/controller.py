import json
import logging
import os
from datetime import datetime
from tempfile import TemporaryDirectory
from zipfile import ZipFile
from lxml import etree

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from packtools.sps.models.v2.article_assets import ArticleAssets
from packtools.sps.pid_provider.xml_sps_lib import XMLWithPre

from article.choices import AS_READ_TO_PUBLISH
from article.models import ArticlePackages
from collection.models import Collection
from core.controller import parse_yyyymmdd
from core.utils.scheduler import schedule_task
from issue.models import Issue, SciELOIssue
from journal.models import Journal, OfficialJournal, SciELOJournal
from scielo_classic_website import classic_ws
from scielo_classic_website.htmlbody.html_body import HTMLContent

from . import exceptions
from .choices import MS_IMPORTED, MS_PUBLISHED, MS_TO_IGNORE, MS_TO_MIGRATE
from .models import (
    BodyAndBackFile,
    ClassicWebsiteConfiguration,
    GeneratedXMLFile,
    MigratedDocument,
    MigratedFile,
    MigratedIssue,
    MigratedJournal,
    MigrationFailure,
)

User = get_user_model()


def schedule_migrations(user, collection_acron=None):
    if collection_acron:
        collections = Collection.objects.filter(acron=collection_acron).iterator()
    else:
        collections = Collection.objects.iterator()
    for collection in collections:
        collection_acron = collection.acron
        _schedule_one_issue_migration(user, collection_acron)
        _schedule_title_db_migration(user, collection_acron)
        _schedule_issue_db_migration(user, collection_acron)
        _schedule_documents_migration(user, collection_acron)
        _schedule_generate_sps_packages(user, collection_acron)
        _schedule_html_to_xmls(user, collection_acron)
        _schedule_run_migrations(user, collection_acron)


def _schedule_title_db_migration(user, collection_acron):
    """
    Agenda a tarefa de migrar os registros da base de dados TITLE
    Deixa a tarefa desabilitada
    """
    schedule_task(
        task="migrate_journal_records",
        name="migrate_journal_records",
        kwargs=dict(
            collection_acron=collection_acron,
            username=user.username,
            force_update=False,
        ),
        description=_("Migra os registros da base de dados TITLE"),
        priority=0,
        enabled=False,
        run_once=True,
        day_of_week="*",
        hour="8",
        minute="5",
    )


def _schedule_issue_db_migration(user, collection_acron):
    """
    Agenda a tarefa de migrar os registros da base de dados ISSUE
    Deixa a tarefa abilitada
    """
    schedule_task(
        task="migrate_issue_records",
        name="migrate_issue_records",
        kwargs=dict(
            collection_acron=collection_acron,
            username=user.username,
            force_update=False,
        ),
        description=_("Migra os registros da base de dados ISSUE"),
        priority=1,
        enabled=True,
        run_once=False,
        day_of_week="*",
        hour="*",
        minute="2,12,22,32,42,52",
    )


def _schedule_documents_migration(user, collection_acron):
    """
    Agenda a tarefa de migrar os arquivos e registros dos artigos
    Deixa a tarefa desabilitada
    Quando usuário quiser executar, deve preencher os valores e executar
    """
    schedule_task(
        task="migrate_document_files_and_records",
        name="migrate_document_files_and_records",
        kwargs=dict(
            username=user.username,
            collection_acron=collection_acron,
            journal_acron=None,
            publication_year=None,
            force_update=False,
        ),
        description=_("Migra os arquivos e registros de artigos"),
        priority=2,
        enabled=False,
        run_once=True,
        day_of_week="*",
        hour="*",
        minute="5,15,25,35,45,55",
    )


def _schedule_one_issue_migration(user, collection_acron):
    """
    Agenda a tarefa de migrar os arquivos e registros dos artigos
    de um dado fascículo
    Deixa a tarefa desabilitada
    Quando usuário quiser executar, deve preencher os valores e executar
    """
    schedule_task(
        task="migrate_one_issue_documents",
        name="migrate_one_issue_documents",
        kwargs=dict(
            username=user.username,
            collection_acron=collection_acron,
            journal_acron=None,
            issue_folder=None,
            force_update=False,
        ),
        description=_("Migra os arquivos e registros de artigos de um dado fascículo"),
        priority=3,
        enabled=False,
        run_once=True,
        day_of_week="*",
        hour="*",
        minute="10",
    )


def _schedule_html_to_xmls(user, collection_acron):
    """
    Agenda a tarefa de gerar os pacotes SPS dos documentos migrados
    Deixa a tarefa desabilitada
    Quando usuário quiser executar, deve preencher os valores e executar
    """
    schedule_task(
        task="html_to_xmls",
        name="html_to_xmls",
        kwargs=dict(
            username=user.username,
            collection_acron=collection_acron,
            journal_acron=None,
            issue_folder=None,
            force_update=False,
        ),
        description=_("Converte HTML em XML"),
        priority=4,
        enabled=False,
        run_once=True,
        day_of_week="*",
        hour="*",
        minute="10",
    )


def _schedule_generate_sps_packages(user, collection_acron):
    """
    Agenda a tarefa de gerar os pacotes SPS dos documentos migrados
    Deixa a tarefa desabilitada
    Quando usuário quiser executar, deve preencher os valores e executar
    """
    schedule_task(
        task="generate_sps_packages",
        name="generate_sps_packages",
        kwargs=dict(
            username=user.username,
            collection_acron=collection_acron,
            journal_acron=None,
            issue_folder=None,
            force_update=False,
        ),
        description=_("Gera os pacotes SPS"),
        priority=4,
        enabled=False,
        run_once=True,
        day_of_week="*",
        hour="*",
        minute="10",
    )


def _schedule_run_migrations(user, collection_acron):
    """
    Agenda a tarefa de migrar os registros da base de dados TITLE
    Deixa a tarefa desabilitada
    """
    schedule_task(
        task="run_migrations",
        name="run_migrations",
        kwargs=dict(
            collection_acron=collection_acron,
            username=user.username,
            force_update=False,
        ),
        description=_("Executa todas as tarefas de migração"),
        priority=1,
        enabled=True,
        run_once=False,
        day_of_week="*",
        hour="1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22",
        minute="5,10,15,20,25,30,35,40,45,50,55",
    )


def get_classic_website(collection_acron):
    config = ClassicWebsiteConfiguration.objects.get(collection__acron=collection_acron)
    return classic_ws.ClassicWebsite(
        bases_path=os.path.join(os.path.dirname(config.bases_work_path), "bases"),
        bases_work_path=config.bases_work_path,
        bases_translation_path=config.bases_translation_path,
        bases_pdf_path=config.bases_pdf_path,
        bases_xml_path=config.bases_xml_path,
        htdocs_img_revistas_path=config.htdocs_img_revistas_path,
        serial_path=config.serial_path,
        cisis_path=config.cisis_path,
        title_path=config.title_path,
        issue_path=config.issue_path,
    )


def migrate_journal_records(
    user,
    collection_acron,
    force_update=False,
):
    collection = Collection.get_or_create(collection_acron)
    classic_website = get_classic_website(collection.acron)
    for scielo_issn, journal_data in classic_website.get_journals_pids_and_records():
        migrated_journal = import_data_from_title_database(
            user,
            collection,
            scielo_issn,
            journal_data[0],
            force_update,
        )


def import_data_from_title_database(
    user,
    collection,
    scielo_issn,
    journal_data,
    classic_website_journal,
    force_update=False,
):
    """
    Create/update JournalMigration
    """
    try:
        # obtém classic website journal
        classic_website_journal = classic_ws.Journal(journal_data)

        year, month, day = parse_yyyymmdd(classic_website_journal.first_year)
        official_journal = OfficialJournal.create_or_update(
            issn_electronic=classic_website_journal.electronic_issn,
            issn_print=classic_website_journal.print_issn,
            title=classic_website_journal.title,
            title_iso=classic_website_journal.title_iso,
            foundation_year=year,
            user=user,
        )
        logging.info(f"Got official_journal {official_journal}")

        journal = Journal.create_or_update(
            official_journal=official_journal,
        )
        logging.info(f"Got journal {journal}")
        # TODO
        # for publisher_name in classic_website_journal.raw_publisher_names:
        #     journal.add_publisher(user, publisher_name)

        scielo_journal = SciELOJournal.create_or_update(
            collection,
            scielo_issn=scielo_issn,
            creator=user,
            official_journal=official_journal,
            acron=classic_website_journal.acronym,
            title=classic_website_journal.title,
            availability_status=classic_website_journal.current_status,
        )
        logging.info(f"Got scielo_journal {scielo_journal}")

        migrated_journal = MigratedJournal.create_or_update(
            scielo_journal=scielo_journal,
            creator=user,
            isis_created_date=classic_website_journal.isis_created_date,
            isis_updated_date=classic_website_journal.isis_updated_date,
            data=journal_data,
            status=MS_IMPORTED,
            force_update=force_update,
        )
        return migrated_journal
    except Exception as e:
        logging.exception(e)
        message = _("Unable to migrate journal {} {}").format(
            collection.acron, scielo_issn
        )
        MigrationFailure.create(
            collection_acron=collection.acron,
            migrated_item_name="journal",
            migrated_item_id=scielo_issn,
            message=message,
            action_name="migrate",
            e=e,
            creator=user,
        )


def migrate_issue_records(
    user,
    collection_acron,
    force_update=False,
):
    """
    Migra os registros da base de dados issue
    """
    collection = Collection.get_or_create(acron=collection_acron)
    classic_website = get_classic_website(collection_acron)
    for issue_pid, issue_data in classic_website.get_issues_pids_and_records():
        migrated_issue = import_data_from_issue_database(
            user=user,
            collection=collection,
            scielo_issn=issue_pid[:9],
            issue_pid=issue_pid,
            issue_data=issue_data[0],
            force_update=force_update,
        )


def import_data_from_issue_database(
    user,
    collection,
    scielo_issn,
    issue_pid,
    issue_data,
    force_update=False,
):
    """
    Create/update IssueMigration
    """
    try:
        logging.info(
            "Import data from database issue {} {} {}".format(
                collection, scielo_issn, issue_pid
            )
        )

        classic_website_issue = classic_ws.Issue(issue_data)

        migrated_journal = MigratedJournal.get(
            collection=collection, scielo_issn=scielo_issn
        )
        issue = Issue.get_or_create(
            official_journal=migrated_journal.scielo_journal.official_journal,
            publication_year=classic_website_issue.publication_year,
            volume=classic_website_issue.volume,
            number=classic_website_issue.number,
            supplement=classic_website_issue.supplement,
            user=user,
        )
        scielo_issue = SciELOIssue.create_or_update(
            scielo_journal=migrated_journal.scielo_journal,
            user=user,
            issue_pid=issue_pid,
            issue_folder=classic_website_issue.issue_label,
            official_issue=issue,
        )
        if classic_website_issue.is_press_release:
            status = MS_TO_IGNORE
        else:
            status = MS_TO_MIGRATE
        logging.info(f"status = {status}")
        migrated_issue = MigratedIssue.create_or_update(
            scielo_issue=scielo_issue,
            migrated_journal=migrated_journal,
            creator=user,
            isis_created_date=classic_website_issue.isis_created_date,
            isis_updated_date=classic_website_issue.isis_updated_date,
            status=status,
            data=issue_data,
            force_update=force_update,
        )
        return migrated_issue
    except Exception as e:
        logging.exception(e)
        message = _("Unable to migrate issue {} {}").format(collection.acron, issue_pid)
        MigrationFailure.create(
            collection_acron=collection.acron,
            migrated_item_name="issue",
            migrated_item_id=issue_pid,
            message=message,
            action_name="migrate",
            e=e,
            creator=user,
        )


class IssueMigration:
    def __init__(self, user, collection_acron, migrated_issue, force_update):
        self.classic_website = get_classic_website(collection_acron)
        self.collection_acron = collection_acron
        self.force_update = force_update
        self.issue_folder = migrated_issue.issue_folder
        self.issue_pid = migrated_issue.issue_pid
        self.migrated_issue = migrated_issue
        self.migrated_journal = migrated_issue.migrated_journal
        self.journal_acron = self.migrated_journal.acron
        self.user = user

    def _get_classic_website_rel_path(self, file_path):
        if "htdocs" in file_path:
            return file_path[file_path.find("htdocs") :]
        if "bases" in file_path:
            return file_path[file_path.find("bases") :]

    def check_category(self, file):
        if file["type"] == "pdf":
            check = file["name"]
            try:
                check = check.replace(file["lang"] + "_", "")
            except (KeyError, TypeError):
                pass
            try:
                check = check.replace(file["key"], "")
            except (KeyError, TypeError):
                pass
            if check == ".pdf":
                return "rendition"
            return "supplmat"
        return file["type"]

    def import_issue_files(self):
        """
        Migra os arquivos do fascículo (pdf, img, xml ou html)
        """
        logging.info(f"Import issue files {self.migrated_issue}")

        classic_issue_files = self.classic_website.get_issue_files(
            self.journal_acron,
            self.issue_folder,
        )
        for file in classic_issue_files:
            """
            {"type": "pdf", "key": name, "path": path, "name": basename, "lang": lang}
            {"type": "xml", "key": name, "path": path, "name": basename, }
            {"type": "html", "key": name, "path": path, "name": basename, "lang": lang, "part": label}
            {"type": "asset", "path": item, "name": os.path.basename(item)}
            """
            try:
                logging.info(f"file: {file}")
                migrated_file = MigratedFile.create_or_update(
                    migrated_issue=self.migrated_issue,
                    original_path=self._get_classic_website_rel_path(file["path"]),
                    source_path=file["path"],
                    category=self.check_category(file),
                    lang=file.get("lang"),
                    part=file.get("part"),
                    pkg_name=file.get("key"),
                    creator=self.user,
                    force_update=self.force_update,
                )
            except Exception as e:
                message = _("Unable to migrate issue files {} {}").format(
                    self.collection_acron, file
                )
                self.register_failure(
                    e,
                    migrated_item_name="issue files",
                    migrated_item_id=file,
                    message=message,
                    action_name="migrate",
                )

    def migrate_document_records(self):
        """
        Importa os registros presentes na base de dados `source_file_path`
        Importa os arquivos dos documentos (xml, pdf, html, imagens)
        Publica os artigos no site
        """
        journal_issue_and_doc_data = {
            "title": self.migrated_journal.data,
            "issue": self.migrated_issue.data,
        }

        logging.info(f"Importing documents records {self.migrated_issue}")
        # obtém registros da base "artigo" que não necessariamente é só
        # do fascículo de migrated_issue
        # possivelmente source_file pode conter registros de outros fascículos
        # se a fonte for `bases-work/acron/acron`
        for doc_id, doc_records in self.classic_website.get_documents_pids_and_records(
            self.journal_acron,
            self.issue_folder,
            self.issue_pid,
        ):
            try:
                logging.info(_("Get self.issue_pid={}").format(self.issue_pid))
                logging.info(_("Get doc_id={}").format(doc_id))
                logging.info(_("records={}").format(len(doc_records)))

                if len(doc_records) == 1:
                    # é possível que em source_file_path exista registro tipo i
                    journal_issue_and_doc_data["issue"] = doc_records[0]
                    continue

                journal_issue_and_doc_data["article"] = doc_records

                logging.info(".......")
                migrated_document = self.migrate_one_document_records(
                    journal_issue_and_doc_data=journal_issue_and_doc_data,
                )
                logging.info(":::::::")

            except Exception as e:
                message = _("Unable to migrate documents {} {} {} {}").format(
                    self.collection_acron, self.journal_acron, self.issue_folder, doc_id
                )
                self.register_failure(
                    e,
                    migrated_item_name="document",
                    migrated_item_id=doc_id,
                    message=message,
                    action_name="migrate",
                )

    def register_failure(
        self, e, migrated_item_name, migrated_item_id, message, action_name
    ):
        logging.info("!!!!!!!!!")
        logging.info(message)
        logging.info(".........")
        logging.exception(e)
        logging.info("_________")
        MigrationFailure.create(
            collection_acron=self.collection_acron,
            migrated_item_name=migrated_item_name,
            migrated_item_id=migrated_item_id,
            message=message,
            action_name=action_name,
            e=e,
            creator=self.user,
        )

    def migrate_one_document_records(self, journal_issue_and_doc_data):
        try:
            logging.info(
                f"migrate_one_document_records: {journal_issue_and_doc_data.keys()}"
            )

            # instancia Document com registros de title, issue e artigo
            classic_ws_doc = classic_ws.Document(journal_issue_and_doc_data)

            # pkg_name
            pkg_name = classic_ws_doc.filename_without_extension
            logging.info(f"pkg_name={pkg_name}")
            logging.info(f"order={classic_ws_doc.order.zfill(5)}")
            logging.info(f"pid={classic_ws_doc.scielo_pid_v2}")

            pid = classic_ws_doc.scielo_pid_v2 or (
                "S" + self.issue_pid + classic_ws_doc.order.zfill(5)
            )
            logging.info(f"pid={pid}")

            if classic_ws_doc.scielo_pid_v2 != pid:
                classic_ws_doc.scielo_pid_v2 = pid

            return MigratedDocument.create_or_update(
                migrated_issue=self.migrated_issue,
                pid=pid,
                pkg_name=pkg_name,
                creator=self.user,
                isis_created_date=classic_ws_doc.isis_created_date,
                isis_updated_date=classic_ws_doc.isis_updated_date,
                data=journal_issue_and_doc_data,
                status=MS_TO_MIGRATE,
                file_type=classic_ws_doc.file_type,
                force_update=self.force_update,
            )
        except Exception as e:
            raise
            migrated_item_id = f"{self.collection_acron} {pid}"
            message = _("Unable to migrate document {}").format(migrated_item_id)
            self.register_failure(
                e,
                migrated_item_name="document",
                migrated_item_id=migrated_item_id,
                message=message,
                action_name="migrate",
            )


def migrate_one_issue_documents(
    user,
    migrated_issue,
    collection_acron,
    force_update=False,
):
    logging.info(f"migrate_one_issue_document: {migrated_issue}")
    migration = IssueMigration(user, collection_acron, migrated_issue, force_update)

    # Melhor importar todos os arquivos e depois tratar da carga
    # dos metadados, e geração de XML, pois
    # há casos que os HTML mencionam arquivos de pastas diferentes
    # da sua pasta do fascículo
    migration.import_issue_files()
    logging.info(f"Imported issue files {migrated_issue}")

    # migra os documentos da base de dados `source_file_path`
    # que não contém necessariamente os dados de só 1 fascículo
    migration.migrate_document_records()
    logging.info(f"Imported records {migrated_issue}")

    # migrated_issue.status = MS_IMPORTED
    # migrated_issue.save()


class DocumentMigration:
    def __init__(self, migrated_document, user):
        self.migrated_document = migrated_document
        self.migrated_issue = migrated_document.migrated_issue
        self.collection_acron = self.migrated_issue.migrated_journal.collection.acron
        self.user = user
        self.pid = migrated_document.pid
        self._xml_name = None
        self._xml_with_pre = None
        self._sps_pkg_name = None
        self.article_pkgs = None
        self.classic_ws_doc = classic_ws.Document(migrated_document.data)
        self.missing_assets = []

    def register_failure(
        self, e, migrated_item_name, migrated_item_id, message, action_name
    ):
        logging.info(message)
        logging.exception(e)
        MigrationFailure.create(
            collection_acron=self.collection_acron,
            migrated_item_name=migrated_item_name,
            migrated_item_id=migrated_item_id,
            message=message,
            action_name=action_name,
            e=e,
            creator=self.user,
        )

    @property
    def xml_with_pre(self):
        logging.info(f"_xml_with_pre = {self._xml_with_pre}")
        if not self._xml_with_pre:
            self._xml_with_pre = self.migrated_document.xml_with_pre
        logging.info(id(self._xml_with_pre.xmltree))
        return self._xml_with_pre

    @property
    def sps_pkg_name(self):
        logging.info(f"_sps_pkg_name = {self._sps_pkg_name}")
        if not self._sps_pkg_name:
            self._sps_pkg_name = self.xml_with_pre.sps_pkg_name
            self.migrated_document.sps_pkg_name = self._sps_pkg_name
            self.migrated_document.save()
        return self._sps_pkg_name

    def build_sps_package(self):
        """
        A partir do XML original ou gerado a partir do HTML, e
        dos ativos digitais, todos registrados em MigratedFile,
        cria o zip com nome no padrão SPS (ISSN-ACRON-VOL-NUM-SUPPL-ARTICLE) e
        o armazena em ArticlePackages.not_optimised_zip_file.
        Neste momento o XML não contém pid v3.
        """
        logging.info(f"Build SPS Package {self.migrated_document}")
        try:
            # gera nome de pacote padrão SPS ISSN-ACRON-VOL-NUM-SUPPL-ARTICLE
            with TemporaryDirectory() as tmpdirname:
                logging.info("TemporaryDirectory %s" % tmpdirname)
                tmp_sps_pkg_zip_path = os.path.join(
                    tmpdirname, f"{self.sps_pkg_name}.zip"
                )

                self.article_pkgs = ArticlePackages.get_or_create(
                    sps_pkg_name=self.sps_pkg_name,
                    creator=self.user,
                )
                with ZipFile(tmp_sps_pkg_zip_path, "w") as zf:
                    # add renditions (pdf) to zip
                    self._build_sps_package_add_renditions(zf)

                    # A partir do XML, obtém os nomes dos arquivos dos ativos digitais
                    article_assets = ArticleAssets(self.xml_with_pre.xmltree)
                    self._build_sps_package_add_assets(zf, article_assets)

                    # adiciona XML em zip
                    self._build_sps_package_add_xml(zf)

                with open(tmp_sps_pkg_zip_path, "rb") as fp:
                    # guarda o pacote compactado
                    self.article_pkgs.add_sps_package_file(
                        filename=self.sps_pkg_name + ".zip",
                        content=fp.read(),
                        user=self.user,
                    )
        except Exception as e:
            message = _("Unable to build sps package {} {}").format(
                self.collection_acron, self.pid
            )
            self.register_failure(
                e,
                migrated_item_name="zip",
                migrated_item_id=self.pid,
                message=message,
                action_name="build-sps-package",
            )

    def _build_sps_package_add_xml(self, zf):
        try:
            sps_xml_name = self.sps_pkg_name + ".xml"
            zf.writestr(sps_xml_name, self.xml_with_pre.tostring())
            self.article_pkgs.add_component(
                sps_filename=sps_xml_name,
                user=self.user,
                category="xml",
            )
        except Exception as e:
            message = _("Unable to _build_sps_package_add_xml {} {} {}").format(
                self.collection_acron, self.sps_pkg_name, sps_xml_name
            )
            self.register_failure(
                e,
                migrated_item_name="xml",
                migrated_item_id=sps_xml_name,
                message=message,
                action_name="build-sps-package",
            )

    def _build_sps_package_add_renditions(self, zf):
        # grava renditions (pdf) em zip
        for rendition_file in MigratedFile.objects.filter(
            migrated_issue=self.migrated_issue,
            pkg_name=self.migrated_document.pkg_name,
            category="rendition",
        ):
            try:
                logging.info(f"Add rendition {rendition_file.original_path}")
                if rendition_file.lang:
                    sps_filename = f"{self.sps_pkg_name}-{rendition_file.lang}.pdf"
                else:
                    sps_filename = f"{self.sps_pkg_name}.pdf"
                zf.write(rendition_file.file.path, arcname=sps_filename)

                self.article_pkgs.add_component(
                    sps_filename=sps_filename,
                    user=self.user,
                    category="rendition",
                    lang=rendition_file.lang,
                    collection_acron=self.collection_acron,
                    former_href=rendition_file.original_href,
                )
            except Exception as e:
                message = _(
                    "Unable to _build_sps_package_add_renditions {} {} {}"
                ).format(self.collection_acron, self.sps_pkg_name, rendition_file)
                self.register_failure(
                    e,
                    migrated_item_name="rendition",
                    migrated_item_id=str(rendition_file),
                    message=message,
                    action_name="build-sps-package",
                )

    def _build_sps_package_add_assets(self, zf, sps_article_assets):
        replacements = {}
        for xml_graphic in sps_article_assets.items:
            logging.info(f"Find asset: {xml_graphic.xlink_href}")
            asset_file = None
            try:
                asset_file = MigratedFile.get(
                    migrated_issue=self.migrated_issue,
                    original_href=xml_graphic.xlink_href,
                )
            except MigratedFile.DoesNotExist as e:
                try:
                    logging.info(f"Try {basename}.*")
                    asset_file = MigratedFile.objects.filter(
                        migrated_issue=self.migrated_issue,
                        original_name__startswith=basename + ".",
                    ).first()
                except MigratedFile.DoesNotExist as e:
                    logging.info(f"Not found {xml_graphic.xlink_href}")
                    self.missing_assets.append(xml_graphic.xlink_href)
            if asset_file:
                self._build_sps_package_add_asset(
                    zf, asset_file, xml_graphic, replacements)

    def _build_sps_package_add_asset(self, zf, asset_file, xml_graphic, replacements):
        try:
            logging.info(f"Add asset {asset_file.original_href}")

            # obtém o nome do arquivo no padrão sps
            sps_filename = xml_graphic.name_canonical(self.sps_pkg_name)
            logging.info(xml_graphic.id)
            logging.info(f"sps filename: {sps_filename}")

            # indica a troca de href original para o padrão SPS
            replacements[asset_file.original_href] = sps_filename
            logging.info(f"replacements: {replacements}")

            # adiciona componente ao pacote
            self.article_pkgs.add_component(
                sps_filename=sps_filename,
                user=self.user,
                category="asset",
                collection_acron=self.collection_acron,
                former_href=asset_file.original_href,
            )
            # adiciona o arquivo no zip
            zf.write(asset_file.file.path, arcname=sps_filename)
        except Exception as e:
            message = _("Unable to _build_sps_package_add_asset {} {} {}").format(
                self.collection_acron, self.sps_pkg_name, asset_file.original_name
            )
            self.register_failure(
                e=e,
                migrated_item_name="asset",
                migrated_item_id=asset_file.original_name,
                message=message,
                action_name="build-sps-package",
            )

    def generate_xml_from_html(self):
        migrated_item_id = f"{self.migrated_document}"

        pkg_name = self.migrated_document.pkg_name
        logging.info(f"DocumentMigration.generate_xml_from_html {pkg_name}")

        classic_ws_doc = self.classic_ws_doc
        try:
            # obtém as traduções
            translated_texts = self.migrated_document.translations
            logging.info(f"translated_texts: {translated_texts}")

            # obtém um XML com body e back a partir dos arquivos HTML / traduções
            classic_ws_doc.generate_body_and_back_from_html(translated_texts)

            logging.info(
                f"classic_ws_doc.xml_body_and_back: {len(classic_ws_doc.xml_body_and_back)}"
            )

            for i, xml_body_and_back in enumerate(classic_ws_doc.xml_body_and_back):
                # guarda cada versão de body/back
                migrated_item_id = f"{self.migrated_document} {i}"
                migrated_file = BodyAndBackFile.create_or_update(
                    migrated_document=self.migrated_document,
                    creator=self.user,
                    file_content=xml_body_and_back,
                    version=i,
                )
        except Exception as e:
            message = _("Unable to generate body and back from HTML {}").format(
                migrated_item_id
            )
            self.register_failure(
                e,
                migrated_item_name="document",
                migrated_item_id=migrated_item_id,
                message=message,
                action_name="xml-body-and-back",
            )
            return

        try:
            xml_body_and_back = classic_ws_doc.xml_body_and_back[-1]
            xml_content = classic_ws_doc.generate_full_xml(xml_body_and_back)
            migrated_file = GeneratedXMLFile.create_or_update(
                migrated_document=self.migrated_document,
                creator=self.user,
                file_content=xml_content,
            )
        except Exception as e:
            migrated_item_id = f"{self.migrated_document}"
            message = _("Unable to generate XML from HTML {}").format(migrated_item_id)
            self.register_failure(
                e,
                migrated_item_name="document",
                migrated_item_id=migrated_item_id,
                message=message,
                action_name="xml-to-html",
            )


def generate_sps_package(collection_acron, user, migrated_document, html_to_xml=False):
    try:
        document_migration = DocumentMigration(migrated_document, user)
        if (
            html_to_xml
            or migrated_document.file_type == "html"
            and not migrated_document.generated_xml
        ):
            logging.info("try to generate xml from html")
            document_migration.generate_xml_from_html()

        logging.info(f"html_to_xml: {html_to_xml}")
        logging.info(f"file_type: {migrated_document.file_type}")
        logging.info(f"generated_xml: {migrated_document.generated_xml}")

        document_migration.build_sps_package()

        # XML_WIP or MISSING_ASSETS or XML_WIP_AND_MISSING_ASSETS
        migrated_document.status = migrated_document.sps_status
        migrated_document.save()

        logging.info(
            f"migrated document: {migrated_document} {migrated_document.status}"
        )
        status = set()
        for item in MigratedDocument.objects.filter(
            migrated_issue=migrated_document.migrated_issue,
        ).iterator():
            status.add(item.status)
        if len(status) == 1 and status == set([MS_IMPORTED]):
            migrated_document.migrated_issue.status = MS_IMPORTED
            migrated_document.migrated_issue.save()
            migrated_document.save()
    except Exception as e:
        migrated_item_id = f"{migrated_document.sps_pkg_name}"
        message = _("Unable to generate SPS Package {}").format(migrated_item_id)
        logging.info(message)
        logging.exception(e)
        MigrationFailure.create(
            collection_acron=collection_acron,
            migrated_item_name="sps_pkg_name",
            migrated_item_id=migrated_item_id,
            message=message,
            action_name="generate_sps_pkg_name",
            e=e,
            creator=user,
        )


def html_to_xml(collection_acron, user, migrated_document):
    generate_sps_package(collection_acron, user, migrated_document, html_to_xml=True)
