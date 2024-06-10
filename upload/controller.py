import logging
import sys
from datetime import datetime
from zipfile import ZIP_DEFLATED, ZipFile

from django.utils.translation import gettext as _
from packtools.sps.models.front_articlemeta_issue import ArticleMetaIssue
from packtools.sps.models.journal_meta import ISSN, Title
from packtools.sps.pid_provider.xml_sps_lib import GetXMLItemsError, XMLWithPre

from article import choices as article_choices
from article.controller import create_article
from article.models import Article
from collection.models import WebSiteConfiguration
from core.utils.requester import fetch_data
from issue.models import Issue
from journal.models import Journal, OfficialJournal
from libs.dsm.publication.db import exceptions, mk_connection
from package import choices as package_choices
from package.models import SPSPkg
from pid_provider.requester import PidRequester
from tracker.models import UnexpectedEvent, serialize_detail
from upload import xml_validation
from upload.models import ValidationReport, XMLErrorReport, XMLInfoReport
from upload.xml_validation import validate_xml_content

from .models import (
    Package,
    choices,
)
from .utils import file_utils, package_utils, xml_utils

pp = PidRequester()


class PackageError(Exception):
    ...


def get_last_package(article_id, **kwargs):
    try:
        return (
            Package.objects.filter(article=article_id, **kwargs)
            .order_by("-created")
            .first()
        )
    except Package.DoesNotExist:
        return


def receive_package(request, package):
    try:
        zip_xml_file_path = package.file.path
        user = request.user
        response = {}
        for xml_with_pre in XMLWithPre.create(path=zip_xml_file_path):
            response = _check_article_and_journal(xml_with_pre, user=user)
            logging.info(response)
            if response.get("xml_changed"):
                # atualiza conteúdo de zip
                with ZipFile(zip_xml_file_path, "a", compression=ZIP_DEFLATED) as zf:
                    zf.writestr(
                        xml_with_pre.filename,
                        xml_with_pre.tostring(pretty_print=True),
                    )

            package.article = response.get("article")
            package.issue = response.get("issue")
            package.journal = response.get("journal")
            package.category = response.get("package_category")
            package.status = response.get("package_status")
            package.save()

            error = response.get("error")
            if error:
                report = ValidationReport.get_or_create(
                    user=user,
                    package=package,
                    title=_("Package file"),
                    category=choices.VAL_CAT_PACKAGE_FILE,
                )
                report.add_validation_result(
                    status=choices.VALIDATION_RESULT_FAILURE,
                    message=response["error"],
                    data=serialize_detail(response),
                    subject=choices.VAL_CAT_PACKAGE_FILE,
                )
                # falhou, retorna response
                return response

            if package.article:
                package.article.change_status_to_submitted()
            return response
    except GetXMLItemsError as exc:
        # identifica os erros do arquivo Zip / XML
        # TODO levar este código para o packtools / XMLWithPre
        return _identify_file_error(package)


def _identify_file_error(package):
    # identifica os erros do arquivo Zip / XML
    # TODO levar este código para o packtools / XMLWithPre
    try:
        xml_path = None
        xml_str = file_utils.get_xml_content_from_zip(package.file.path, xml_path)
        xml_utils.get_etree_from_xml_content(xml_str)
        return {}
    except (
        file_utils.BadPackageFileError,
        file_utils.PackageWithoutXMLFileError,
    ) as exc:
        message = exc.message
        data = None

    except xml_utils.XMLFormatError as e:
        data = {
            "column": e.column,
            "row": e.start_row,
            "snippet": xml_utils.get_snippet(xml_str, e.start_row, e.end_row),
        }
        message = e.message

    report = ValidationReport.get_or_create(
        package.creator, package, _("File Report"), choices.VAL_CAT_PACKAGE_FILE
    )
    validation_result = report.add_validation_result(
        status=choices.VALIDATION_RESULT_FAILURE,
        message=message,
        data=data,
    )
    return {"error": message}


def _check_article_and_journal(xml_with_pre, user):
    # verifica se o XML está registrado no sistema
    response = {}
    try:
        response = pp.is_registered_xml_with_pre(xml_with_pre, xml_with_pre.filename)
        # verifica se o XML é esperado (novo, requer correção, requer atualização)
        _check_package_is_expected(response)

        # verifica se journal e issue estão registrados
        xmltree = xml_with_pre.xmltree

        _check_journal(response, xmltree, user)
        _check_issue(response, xmltree, user)

        # verifica a consistência dos dados de journal e issue
        # no XML e na base de dados
        _check_xml_and_registered_data_compability(response)

        response["package_status"] = choices.PS_ENQUEUED_FOR_VALIDATION
        return response
    except PackageError as e:
        response["package_status"] = choices.PS_REJECTED
        response["error"] = str(e)
        return response


def _check_package_is_expected(response):

    try:
        article = Article.objects.get(pid_v3=response["v3"])
    except (Article.DoesNotExist, KeyError):
        # TODO verificar journal, issue
        response["article"] = None
        response["package_category"] = choices.PC_NEW_DOCUMENT
    else:
        response["article"] = article
        try:
            package_status = {
                article_choices.AS_REQUIRE_UPDATE: choices.PC_UPDATE,
                article_choices.AS_REQUIRE_ERRATUM: choices.PC_ERRATUM,
            }
            response["package_category"] = package_status[article.status]
        except KeyError:
            response["package_category"] = choices.PS_REJECTED
            raise PackageError(
                f"Unexpected package. Article has no need to be updated / corrected. Article status: {article.status}"
            )


def _check_journal(response, xmltree, user):
    xml = Title(xmltree)
    journal_title = xml.journal_title

    xml = ISSN(xmltree)
    issn_electronic = xml.epub
    issn_print = xml.ppub

    response["journal"] = Journal.exists(
        journal_title, issn_electronic, issn_print, user
    )
    if not response["journal"]:
        raise PackageError(
            f"Not registered journal: {journal_title} {issn_electronic} {issn_print}"
        )


def _check_issue(response, xmltree, user):
    xml = ArticleMetaIssue(xmltree)
    response["issue"] = Issue.exists(
        response["journal"], xml.volume, xml.suppl, xml.number, user
    )
    if not response["issue"]:
        raise PackageError(
            f"Not registered issue: {response['journal']} {xml.volume} {xml.number} {xml.suppl}"
        )


def _check_xml_and_registered_data_compability(response):
    article = response["article"]

    if article:
        journal = response["journal"]
        if journal is not article.journal:
            raise PackageError(
                f"{article.journal} (registered) differs from {journal} (XML)"
            )

        issue = response["issue"]
        if issue is not article.issue:
            raise PackageError(
                f"{article.issue} (registered) differs from {issue} (XML)"
            )


def validate_xml_content(package, journal, issue):
    try:
        for xml_with_pre in XMLWithPre.create(path=package.file.path):
            _validate_xml_content(xml_with_pre, package, journal, issue)
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        UnexpectedEvent.create(
            exception=e,
            exc_traceback=exc_traceback,
            detail={
                "operation": "upload.controller.validate_xml_content",
                "detail": dict(file_path=package.file.path),
            },
        )


def _validate_xml_content(xml_with_pre, package, journal, issue):

    try:
        info_report = XMLInfoReport.get_or_create(
            package.creator, package, _("XML Info Report"), choices.VAL_CAT_XML_CONTENT
        )
        error_report = XMLErrorReport.get_or_create(
            package.creator, package, _("XML Error Report"), choices.VAL_CAT_XML_CONTENT
        )

        results = xml_validation.validate_xml_content(
            xml_with_pre.sps_pkg_name, xml_with_pre.xmltree, journal, issue
        )
        for result in results:
            _handle_xml_content_validation_result(
                package,
                xml_with_pre.sps_pkg_name,
                result,
                info_report,
                error_report,
            )
        info_report.finish_validations()
        for error_report in package.xml_error_report.all():
            if error_report.xml_error.count():
                error_report.finish_validations()
            else:
                error_report.delete()
        # devido às tarefas serem executadas concorrentemente,
        # necessário verificar se todas tarefas finalizaram e
        # então finalizar o pacote
        package.finish_validations()

    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        UnexpectedEvent.create(
            exception=e,
            exc_traceback=exc_traceback,
            detail={
                "operation": "upload.controller._validate_xml_content",
                "detail": {
                    "file": package.file.path,
                    "item": xml_with_pre.sps_pkg_name,
                    "exception": str(e),
                    "exception_type": str(type(e)),
                },
            },
        )


def _handle_xml_content_validation_result(
    package, sps_pkg_name, result, info_report, error_report
):
    # ['xpath', 'advice', 'title', 'expected_value', 'got_value', 'message', 'validation_type', 'response']

    try:
        status_ = result["response"]
        if status_ == "OK":
            report = info_report
        else:

            group = result.get("group") or result.get("item")
            if not group and result.get("exception_type"):
                group = "configuration"
            if group:
                report = XMLErrorReport.get_or_create(
                    package.creator,
                    package,
                    _("XML Error Report") + f": {group}",
                    group,
                )
            else:
                report = error_report

        message = result.get("message") or ""
        advice = result.get("advice") or ""
        message = ". ".join([_(message), _(advice)])

        validation_result = report.add_validation_result(
            status=status_,
            message=result.get("message"),
            data=result,
            subject=result.get("item"),
        )
        validation_result.focus = result.get("title")
        validation_result.attribute = result.get("sub_item")
        validation_result.parent = result.get("parent")
        validation_result.parent_id = result.get("parent_id")
        validation_result.parent_article_type = result.get("parent_article_type")
        validation_result.validation_type = result.get("validation_type") or "xml"

        if status_ == choices.VALIDATION_RESULT_FAILURE:
            validation_result.advice = result.get("advice")
            validation_result.expected_value = result.get("expected_value")
            validation_result.got_value = result.get("got_value")
            validation_result.reaction = choices.ER_REACTION_FIX

        validation_result.save()
        return validation_result
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        UnexpectedEvent.create(
            exception=e,
            exc_traceback=exc_traceback,
            detail={
                "operation": "upload.controller._handle_xml_content_validation_result",
                "detail": {
                    "file": package.file.path,
                    "item": sps_pkg_name,
                    "result": result,
                    "exception": str(e),
                    "exception_type": str(type(e)),
                },
            },
        )
