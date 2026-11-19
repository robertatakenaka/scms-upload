"""
Upload: complementação de coleções do periódico Psicologia USP, presente em
scl (PID 0103-6564, coleção principal) e psi (PID 1678-5177)
"""

from unittest.mock import patch
from zipfile import ZipFile

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.urls import reverse
from packtools.sps.pid_provider.xml_sps_lib import get_xml_with_pre

from collection_completion import choices, handlers, tasks
from collection_completion.models import CollectionCompletion
from issue.models import Issue
from journal.models import Journal
from package.models import SPSPkg
from pid_provider.tests.test_register_multi_collection import (
    PSI_V2,
    SCL_V2,
    RegisterSameArticleInDifferentCollectionsTestBase,
    scl_xml,
)
from proc.models import ArticleProc, IssueProc, JournalProc
from tracker import choices as tracker_choices

User = get_user_model()

SCL_ISSUE_PID = "0103-656420090003"
PSI_ISSUE_PID = "1678-517720090003"
PID_V3 = "Pv3sclpsi00000000000003"


def make_zip_content(xml_with_pre):
    from io import BytesIO

    content = BytesIO()
    with ZipFile(content, "w") as zf:
        zf.writestr("0103-6564-pusp-20-03-00003.xml", xml_with_pre.tostring())
        zf.writestr("0103-6564-pusp-20-03-00003.pdf", b"%PDF")
    return content.getvalue()


class UploadCollectionCompletionTestBase(RegisterSameArticleInDifferentCollectionsTestBase):
    """
    Fascículo em scl e psi (obtidos do Core); artigo somente em scl
    """

    def setUp(self):
        super().setUp()
        self.journal = Journal.objects.get()
        self.issue = Issue.objects.create(
            journal=self.journal,
            publication_year="2009",
            volume="20",
            number="3",
            creator=self.user,
        )
        self.scl_issue_proc = IssueProc.objects.create(
            collection=self.scl,
            pid=SCL_ISSUE_PID,
            issue=self.issue,
            journal_proc=JournalProc.objects.get(collection=self.scl),
            creator=self.user,
        )
        self.psi_issue_proc = IssueProc.objects.create(
            collection=self.psi,
            pid=PSI_ISSUE_PID,
            issue=self.issue,
            journal_proc=JournalProc.objects.get(collection=self.psi),
            creator=self.user,
        )
        xml_with_pre = scl_xml()
        xml_with_pre.v3 = PID_V3
        self.sps_pkg = SPSPkg.objects.create(
            pid_v3=PID_V3,
            pid_v2=SCL_V2,
            sps_pkg_name="0103-6564-pusp-20-03-00003",
            registered_in_core=True,
            texts={"xml_langs": ["pt"], "pdf_langs": ["pt"]},
            creator=self.user,
        )
        self.sps_pkg.file.save(
            "0103-6564-pusp-20-03-00003.zip", ContentFile(make_zip_content(xml_with_pre))
        )
        self.article_proc = ArticleProc.objects.create(
            collection=self.scl,
            pid=SCL_V2,
            issue_proc=self.scl_issue_proc,
            pkg_name="0103-6564-pusp-20-03-00003",
            sps_pkg=self.sps_pkg,
            creator=self.user,
        )

    def complete_issue(self):
        return handlers.complete_issue(
            self.user, self.journal, self.scl, self.psi, self.scl_issue_proc.pk
        )

    def complete_article(self):
        return handlers.complete_article(
            self.user, self.scl, self.psi, self.article_proc.pk, self.psi_issue_proc.pk
        )


def fake_sps_pkg_create_or_update(
    user, sps_pkg_zip_path, origin, is_public, original_pkg_components, texts, article_proc
):
    """
    Simula SPSPkg.create_or_update (pid provider e MinIO), guardando o XML
    recebido
    """
    with ZipFile(sps_pkg_zip_path) as zf:
        xml_name = [name for name in zf.namelist() if name.endswith(".xml")][0]
        xml_with_pre = get_xml_with_pre(zf.read(xml_name).decode("utf-8"))
    obj = SPSPkg.objects.create(
        pid_v3=xml_with_pre.v3,
        pid_v2=xml_with_pre.v2,
        sps_pkg_name="1678-5177-psicousp-20-03-00003",
        registered_in_core=True,
        creator=user,
    )
    fake_sps_pkg_create_or_update.received = {
        "v2": xml_with_pre.v2,
        "v3": xml_with_pre.v3,
        "collection": xml_with_pre.collection,
        "components": original_pkg_components,
        "texts": texts,
        "article_proc": article_proc,
    }
    return obj


class GetJournalsAndIssuesTest(UploadCollectionCompletionTestBase):
    def test_journal_in_more_than_one_collection(self):
        self.assertEqual(list(handlers.get_journals_queryset()), [self.journal])
        self.assertCountEqual(
            handlers.get_journal_collections(self.journal), [self.scl, self.psi]
        )

    def test_source_issues(self):
        self.assertEqual(
            handlers.get_source_issues(self.journal, self.scl, self.psi, ["2009"]),
            [
                {
                    "id": str(self.scl_issue_proc.pk),
                    "label": "2009 v.20 n.3",
                    "source_pid": SCL_ISSUE_PID,
                    "target_pid": PSI_ISSUE_PID,
                }
            ],
        )
        self.assertEqual(
            handlers.get_source_issues(self.journal, self.scl, self.psi, ["2010"]), []
        )


class CompleteIssueTest(UploadCollectionCompletionTestBase):
    def test_issue_in_target_collection(self):
        response = self.complete_issue()

        # o Upload não completa fascículos
        self.assertEqual(response["status"], choices.STATUS_IGNORED)
        self.assertEqual(response["target_pid"], PSI_ISSUE_PID)
        self.assertEqual(response["target_issue_id"], self.psi_issue_proc.pk)
        self.assertEqual(
            response["articles"],
            [
                {
                    "id": str(self.article_proc.pk),
                    "label": "0103-6564-pusp-20-03-00003",
                    "pid": SCL_V2,
                }
            ],
        )

    def test_issue_not_in_target_collection(self):
        self.psi_issue_proc.delete()

        response = self.complete_issue()

        self.assertEqual(response["status"], choices.STATUS_IGNORED)
        self.assertIsNone(response.get("target_issue_id"))
        self.assertIn("Core", response["reason"])
        self.assertEqual(IssueProc.objects.filter(collection=self.psi).count(), 0)


@patch("collection_completion.handlers.Article.create_or_update")
@patch(
    "collection_completion.handlers.SPSPkg.create_or_update",
    side_effect=fake_sps_pkg_create_or_update,
)
class CompleteArticleTest(UploadCollectionCompletionTestBase):
    def test_article_is_added_with_the_target_pid_v2(self, create_sps_pkg, create_article):
        response = self.complete_article()

        self.assertEqual(response["status"], choices.STATUS_ADDED, response)
        self.assertEqual(response["source_pid"], SCL_V2)
        self.assertEqual(response["target_pid"], PSI_V2)

        target = ArticleProc.objects.get(collection=self.psi)
        self.assertEqual(target.pid, PSI_V2)
        self.assertEqual(target.issue_proc, self.psi_issue_proc)
        self.assertEqual(target.migration_status, tracker_choices.PROGRESS_STATUS_DONE)
        self.assertEqual(target.sps_pkg_status, tracker_choices.PROGRESS_STATUS_DONE)
        # não publica
        self.assertNotEqual(target.qa_ws_status, tracker_choices.PROGRESS_STATUS_DONE)
        self.assertNotEqual(target.public_ws_status, tracker_choices.PROGRESS_STATUS_DONE)

        # XML da coleção origem com o pid v2 e a coleção destino
        received = fake_sps_pkg_create_or_update.received
        self.assertEqual(received["v2"], PSI_V2)
        self.assertEqual(received["v3"], PID_V3)
        self.assertEqual(received["collection"], "psi")
        self.assertEqual(received["article_proc"], target)
        self.assertEqual(received["texts"], self.sps_pkg.texts)

        create_article.assert_called_once_with(
            self.user,
            target.sps_pkg,
            issue=self.issue,
            journal=self.journal,
            collection=self.psi,
        )
        # pacote da origem não é alterado
        self.sps_pkg.refresh_from_db()
        self.assertEqual(self.sps_pkg.pid_v2, SCL_V2)

    def test_article_already_in_target_collection_is_ignored(
        self, create_sps_pkg, create_article
    ):
        self.complete_article()
        create_sps_pkg.reset_mock()

        response = self.complete_article()

        self.assertEqual(response["status"], choices.STATUS_IGNORED)
        create_sps_pkg.assert_not_called()

    def test_pid_used_by_another_article_is_ignored(self, create_sps_pkg, create_article):
        other_pkg = SPSPkg.objects.create(pid_v3="other", creator=self.user)
        ArticleProc.objects.create(
            collection=self.psi, pid=PSI_V2, sps_pkg=other_pkg, creator=self.user
        )

        response = self.complete_article()

        self.assertEqual(response["status"], choices.STATUS_IGNORED)
        self.assertIn("other", response["reason"])
        create_sps_pkg.assert_not_called()

    def test_document_already_in_target_collection_with_another_pid(
        self, create_sps_pkg, create_article
    ):
        other_pkg = SPSPkg.objects.create(pid_v3=PID_V3, creator=self.user)
        ArticleProc.objects.create(
            collection=self.psi,
            pid="S1678-51772009000300099",
            sps_pkg=other_pkg,
            creator=self.user,
        )

        response = self.complete_article()

        self.assertEqual(response["status"], choices.STATUS_IGNORED)
        self.assertIn("S1678-51772009000300099", response["reason"])
        create_sps_pkg.assert_not_called()

    def test_article_without_sps_pkg_is_ignored(self, create_sps_pkg, create_article):
        ArticleProc.objects.filter(pk=self.article_proc.pk).update(sps_pkg=None)

        response = self.complete_article()

        self.assertEqual(response["status"], choices.STATUS_IGNORED)
        self.assertFalse(ArticleProc.objects.filter(collection=self.psi).exists())

    def test_sps_pkg_failure_is_an_error(self, create_sps_pkg, create_article):
        create_sps_pkg.side_effect = None
        create_sps_pkg.return_value = None

        response = self.complete_article()

        self.assertEqual(response["status"], choices.STATUS_ERROR)
        create_article.assert_not_called()


class CollectionCompletionTasksTest(UploadCollectionCompletionTestBase):
    def test_articles_are_ignored_when_the_issue_is_not_in_target_collection(self):
        self.psi_issue_proc.delete()
        completion = CollectionCompletion.create(
            self.user, self.journal, self.scl, self.psi, 2009, 2009
        )
        item = completion.add_item(
            self.user, choices.ITEM_TYPE_ISSUE, self.scl_issue_proc.pk
        )

        with patch.object(tasks.task_complete_article, "apply_async") as apply_async:
            tasks.task_complete_issue(item_id=item.pk, user_id=self.user.pk)

        apply_async.assert_not_called()
        self.assertTrue(completion.is_finished)
        self.assertEqual(
            completion.totals,
            {"issue": {"ignored": 1}, "article": {"ignored": 1}},
        )

    @patch("collection_completion.handlers.Article.create_or_update")
    @patch(
        "collection_completion.handlers.SPSPkg.create_or_update",
        side_effect=fake_sps_pkg_create_or_update,
    )
    def test_issue_task_dispatches_the_article_tasks(self, create_sps_pkg, create_article):
        completion = CollectionCompletion.create(
            self.user, self.journal, self.scl, self.psi, 2009, 2009
        )
        item = completion.add_item(
            self.user, choices.ITEM_TYPE_ISSUE, self.scl_issue_proc.pk
        )

        with patch.object(tasks.task_complete_article, "apply_async") as apply_async:
            with self.captureOnCommitCallbacks(execute=True):
                tasks.task_complete_issue(item_id=item.pk, user_id=self.user.pk)

        article_item = item.children.get()
        apply_async.assert_called_once_with(
            kwargs={
                "item_id": article_item.pk,
                "user_id": self.user.pk,
                "target_issue_id": self.psi_issue_proc.pk,
            }
        )
        tasks.task_complete_article(**apply_async.call_args.kwargs["kwargs"])

        self.assertTrue(completion.is_finished)
        self.assertEqual(
            completion.totals,
            {"issue": {"ignored": 1}, "article": {"added": 1}},
        )


class CollectionCompletionViewsTest(UploadCollectionCompletionTestBase):
    def form_data(self):
        return {
            "journal": self.journal.pk,
            "source_collection": self.scl.pk,
            "target_collection": self.psi.pk,
            "start_year": 2009,
            "end_year": 2009,
        }

    def test_only_admin_users(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("collection_completion:list"))
        self.assertIn(response.status_code, (302, 403))

    def test_form_lists_issues_and_confirmation_dispatches_tasks(self):
        admin = User.objects.create_superuser(username="admin", password="x")
        self.client.force_login(admin)

        response = self.client.post(
            reverse("collection_completion:create"), self.form_data()
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, SCL_ISSUE_PID)

        data = {**self.form_data(), "issues": [str(self.scl_issue_proc.pk)]}
        with patch.object(tasks.task_complete_issue, "apply_async") as apply_async:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    reverse("collection_completion:confirm"), data
                )

        completion = CollectionCompletion.objects.get()
        item = completion.items.get()
        apply_async.assert_called_once_with(
            kwargs={"item_id": item.pk, "user_id": admin.pk}
        )
        response = self.client.get(
            reverse("collection_completion:report", args=[completion.pk])
        )
        self.assertEqual(response.status_code, 200)
