"""
Upload: regras da complementação de coleções (ver models.py)

No Upload, fascículos e artigos são registrados por coleção: IssueProc e
ArticleProc (collection + pid). Cada documento tem um pacote SPS (SPSPkg) e
um Article por coleção, vinculados ao documento na coleção
(CollectionPidV2) no pid provider.

Completar a coleção destino:
- fascículo: o Upload não completa fascículos, pois não envia dados de
  fascículos ao Core; o fascículo deve existir na coleção destino
  (IssueProc), obtido do Core. Se não existe, o fascículo e os seus artigos
  são ignorados (completar o fascículo no Core e obtê-lo no Upload)
- artigo: cria o ArticleProc da coleção destino com o pid v2 da coleção
  destino (S + PID do fascículo na coleção destino + ordem do artigo na
  coleção origem) e gera o SPSPkg e o Article da coleção destino a partir do
  pacote da coleção origem, com o XML com o pid v2 e a coleção destino,
  registrado no pid provider (que o envia ao Core)

Não publica o conteúdo: qa_ws_status / public_ws_status ficam como os de um
artigo novo, a publicar por outra ação.

Mesma interface de handlers.py do Core, cujas regras são outras (o Core
completa fascículos)
"""

import os
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

from django.db.models import Count
from django.utils.translation import gettext as _
from packtools.sps.pid_provider.xml_sps_lib import get_xml_with_pre

from article.models import Article
from collection.models import Collection
from collection_completion import choices
from collection_completion.pids import build_article_pid, is_valid_article_pid
from journal.models import Journal
from package.models import SPSPkg
from pid_provider.models import CollectionPidV2
from proc.models import ArticleProc, IssueProc, JournalProc
from tracker import choices as tracker_choices


def result(status, reason=None, **kwargs):
    return {"status": status, "reason": reason and str(reason), **kwargs}


def get_journals_queryset():
    """
    Periódicos presentes em mais de uma coleção
    """
    journal_ids = (
        JournalProc.objects.filter(journal__isnull=False, collection__isnull=False)
        .values("journal")
        .annotate(total=Count("collection", distinct=True))
        .filter(total__gt=1)
        .values("journal")
    )
    return Journal.objects.filter(id__in=journal_ids).order_by("title")


def get_journal_collections(journal):
    return list(
        Collection.objects.filter(
            id__in=JournalProc.objects.filter(journal=journal).values("collection")
        )
    )


def get_issue_label(issue):
    if not issue:
        return ""
    parts = [issue.publication_year]
    if issue.volume:
        parts.append(f"v.{issue.volume}")
    if issue.number:
        parts.append(f"n.{issue.number}")
    if issue.supplement:
        parts.append(f"s.{issue.supplement}")
    return " ".join(str(part) for part in parts if part)


def get_target_issue_proc(issue_proc, target_collection):
    if not issue_proc.issue_id:
        return None
    return IssueProc.objects.filter(
        collection=target_collection, issue_id=issue_proc.issue_id
    ).first()


def get_source_issues(journal, source_collection, target_collection, years):
    """
    Fascículos (IssueProc) do periódico, dos anos informados, da coleção
    origem

    Returns
    -------
    list of dict
        [{"id", "label", "source_pid", "target_pid"}]
        target_pid: PID do fascículo, se já está na coleção destino
    """
    items = []
    issue_procs = (
        IssueProc.objects.filter(
            collection=source_collection,
            journal_proc__journal=journal,
            issue__publication_year__in=years,
        )
        .select_related("issue")
        .order_by("issue__publication_year", "pid")
    )
    for issue_proc in issue_procs:
        target = get_target_issue_proc(issue_proc, target_collection)
        items.append(
            {
                "id": str(issue_proc.pk),
                "label": get_issue_label(issue_proc.issue),
                "source_pid": issue_proc.pid,
                "target_pid": target and target.pid,
            }
        )
    return items


def get_source_articles(issue_proc):
    return [
        {
            "id": str(article_proc.pk),
            "label": article_proc.pkg_name or article_proc.pid,
            "pid": article_proc.pid,
        }
        for article_proc in ArticleProc.objects.filter(
            issue_proc=issue_proc, collection=issue_proc.collection
        ).order_by("pid", "pk")
    ]


def complete_issue(user, journal, source_collection, target_collection, issue_id):
    """
    Verifica se o fascículo está na coleção destino (o Upload não completa
    fascículos)

    Returns
    -------
    dict
        {"status", "reason", "source_pid", "target_pid", "target_issue_id",
        "articles": [{"id", "label", "pid"}]}
        target_issue_id: IssueProc.id do fascículo na coleção destino, senão
        None (os artigos não são completados)
    """
    issue_proc = IssueProc.objects.select_related("issue").get(
        pk=issue_id, collection=source_collection, journal_proc__journal=journal
    )
    data = {
        "source_pid": issue_proc.pid,
        "articles": get_source_articles(issue_proc),
    }
    target = get_target_issue_proc(issue_proc, target_collection)
    if not target:
        return result(
            choices.STATUS_IGNORED,
            _(
                "The issue is not in the target collection. Issues are completed "
                "in Core; then the issue must be obtained from Core"
            ),
            **data,
        )
    return result(
        choices.STATUS_IGNORED,
        _("The issue is already in the target collection"),
        target_pid=target.pid,
        target_issue_id=target.pk,
        **data,
    )


def get_pkg_components(sps_pkg):
    """
    Componentes do pacote da coleção origem (ver SPSPkg.upload_components_to_the_cloud)
    """
    return {
        component.basename: {
            "component_type": component.component_type,
            "lang": component.lang and component.lang.code2,
            "legacy_uri": component.legacy_uri,
        }
        for component in sps_pkg.components.select_related("lang").all()
        if component.basename
    }


def build_target_zip(source_zip_path, target_zip_path, target_pid, target_acron):
    """
    Cópia do pacote com o XML com o pid v2 e a coleção (custom-meta) da
    coleção destino
    """
    with ZipFile(source_zip_path) as source:
        with ZipFile(target_zip_path, "w", compression=ZIP_DEFLATED) as target:
            for name in source.namelist():
                content = source.read(name)
                if name.endswith(".xml"):
                    xml_with_pre = get_xml_with_pre(content.decode("utf-8"))
                    xml_with_pre.v2 = target_pid
                    xml_with_pre.collection = target_acron
                    content = xml_with_pre.tostring()
                target.writestr(name, content)


def complete_article(user, source_collection, target_collection, article_id, target_issue_id):
    """
    Adiciona o artigo à coleção destino: ArticleProc, SPSPkg e Article da
    coleção destino

    Returns
    -------
    dict
        {"status", "reason", "source_pid", "target_pid", "detail"}
    """
    source = ArticleProc.objects.select_related("sps_pkg").get(
        pk=article_id, collection=source_collection
    )
    target_issue_proc = IssueProc.objects.select_related(
        "issue", "journal_proc__journal"
    ).get(pk=target_issue_id, collection=target_collection)
    source_pid = source.pid
    data = {"source_pid": source_pid}

    if not is_valid_article_pid(source_pid):
        return result(
            choices.STATUS_IGNORED,
            _("The article has no valid PID v2 in the source collection: {}").format(
                source_pid
            ),
            **data,
        )
    target_pid = build_article_pid(target_issue_proc.pid, source_pid)
    if not target_pid:
        return result(
            choices.STATUS_IGNORED,
            _("Unable to build the article PID: issue PID in the target collection {}").format(
                target_issue_proc.pid
            ),
            **data,
        )
    data["target_pid"] = target_pid

    sps_pkg = source.sps_pkg
    if not sps_pkg or not sps_pkg.file or not sps_pkg.pid_v3:
        return result(
            choices.STATUS_IGNORED,
            _("The article has no SPS package in the source collection"),
            **data,
        )
    pid_v3 = sps_pkg.pid_v3

    target = ArticleProc.objects.filter(
        collection=target_collection, pid=target_pid
    ).select_related("sps_pkg").first()
    if target and target.sps_pkg:
        if target.sps_pkg.pid_v3 == pid_v3:
            return result(
                choices.STATUS_IGNORED,
                _("The article is already in the target collection"),
                **data,
            )
        return result(
            choices.STATUS_IGNORED,
            _("The PID {} is already used by another article in the target collection (PID v3 {})").format(
                target_pid, target.sps_pkg.pid_v3
            ),
            **data,
        )

    other = (
        ArticleProc.objects.filter(collection=target_collection, sps_pkg__pid_v3=pid_v3)
        .exclude(pid=target_pid)
        .first()
    )
    if other:
        return result(
            choices.STATUS_IGNORED,
            _("The document is already in the target collection with the PID v2 {}").format(
                other.pid
            ),
            **data,
        )
    collection_pid_v2 = (
        CollectionPidV2.objects.filter(collection=target_collection)
        .filter(pid_v2=target_pid)
        .exclude(pid_provider_xml__v3=pid_v3)
        .first()
    )
    if collection_pid_v2:
        return result(
            choices.STATUS_IGNORED,
            _("The PID {} is already registered for another document (PID v3 {}) in the target collection").format(
                target_pid, collection_pid_v2.pid_provider_xml and collection_pid_v2.pid_provider_xml.v3
            ),
            **data,
        )
    collection_pid_v2 = (
        CollectionPidV2.objects.filter(
            collection=target_collection, pid_provider_xml__v3=pid_v3
        )
        .exclude(pid_v2=target_pid)
        .first()
    )
    if collection_pid_v2:
        return result(
            choices.STATUS_IGNORED,
            _("The document is already registered in the target collection with the PID v2 {}").format(
                collection_pid_v2.pid_v2
            ),
            **data,
        )

    target = target or ArticleProc.get_or_create(user, target_collection, target_pid)
    target.issue_proc = target_issue_proc
    target.pkg_name = source.pkg_name
    target.main_lang = source.main_lang
    target.updated_by = user
    target.save()

    with TemporaryDirectory() as tmpdir:
        zip_path = os.path.join(tmpdir, os.path.basename(sps_pkg.file.name))
        build_target_zip(sps_pkg.file.path, zip_path, target_pid, target_collection.acron)
        target_sps_pkg = SPSPkg.create_or_update(
            user,
            zip_path,
            origin=sps_pkg.origin,
            is_public=sps_pkg.is_public,
            original_pkg_components=get_pkg_components(sps_pkg),
            texts=sps_pkg.texts,
            article_proc=target,
        )

    target.sps_pkg = target_sps_pkg
    target.xml_status = tracker_choices.PROGRESS_STATUS_DONE
    target.update_sps_pkg_status()
    if not target_sps_pkg:
        return result(
            choices.STATUS_ERROR,
            _("Unable to create the SPS package of the target collection (see the ArticleProc events)"),
            **data,
        )

    registered_pid_v2 = target_sps_pkg.get_pid_v2()
    if registered_pid_v2 != target_pid:
        return result(
            choices.STATUS_ERROR,
            _("Unexpected PID v2 registered: {} (expected {})").format(
                registered_pid_v2, target_pid
            ),
            **data,
        )

    Article.create_or_update(
        user,
        target_sps_pkg,
        issue=target_issue_proc.issue,
        journal=target_issue_proc.journal_proc and target_issue_proc.journal_proc.journal,
        collection=target_collection,
    )
    target.migration_status = tracker_choices.PROGRESS_STATUS_DONE
    target.updated_by = user
    target.save()

    return result(
        choices.STATUS_ADDED,
        detail={
            "v3": target_sps_pkg.pid_v3,
            "v2": registered_pid_v2,
            "sps_pkg_name": target_sps_pkg.sps_pkg_name,
            "registered_in_core": target_sps_pkg.registered_in_core,
        },
        **data,
    )
