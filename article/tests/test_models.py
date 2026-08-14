"""
- Article.get(pid_v2=None, sps_pkg_name=None, pid_v3=None, sps_pkg=None)
- Article.delete_related_items(qs)
- Article.create_or_update(user, sps_pkg, issue=None, journal=None, position=None)
- Article.get_repeated_values(field_name, queryset=None, issue=None)
- Article.exclude_invalid_records(user, issue, sps_pkg_id_list, timeout=None)
- Article._exclude_invalid_records(user, issue, sps_pkg_id_list, timeout=None)
- Article.fix_sps_pkg_names(items=None)

"""

import unittest
from unittest.mock import DEFAULT, MagicMock, Mock, patch

from django.contrib.auth import get_user_model

from article.models import Article
from issue.models import Issue
from journal.models import Journal
from package.models import SPSPkg

User = get_user_model()


def _mock_model_instance(model_cls, **attrs):
    """Cria um Mock(spec=model_cls) utilizável em assignments de ForeignKey.

    O ForwardManyToOneDescriptor do Django, ao fazer `obj.campo_fk = valor`,
    consulta o db router, que acessa `valor._state.db`. `_state` é um
    atributo de INSTÂNCIA (criado em Model.__init__), não de classe — por
    isso não aparece no spec de `Mock(spec=ModelClass)`, e a leitura de
    `mock._state` levanta AttributeError. Aqui atribuímos um `_state` fake
    manualmente (escrita de atributo novo é permitida com `spec` simples,
    só a leitura de atributos fora do spec é bloqueada).
    """
    mock_obj = Mock(spec=model_cls)
    mock_obj._state = Mock(db=None)
    for key, value in attrs.items():
        setattr(mock_obj, key, value)
    return mock_obj


# ============================================================
# Article.get()
# ============================================================


class ArticleGetTestCase(unittest.TestCase):
    """Testes para Article.get().

    get() delega para cls.objects.get(**params) e NÃO trata duplicidade —
    esse tratamento (MultipleObjectsReturned) é responsabilidade de quem
    chama, como create_or_update().
    """

    def test_raises_value_error_without_any_param(self):
        with self.assertRaises(ValueError):
            Article.get()

    @patch("article.models.Article.objects")
    def test_get_by_pid_v3(self, mock_objects):
        mock_article = Mock(spec=Article)
        mock_objects.get.return_value = mock_article

        result = Article.get(pid_v3="pid123")

        self.assertEqual(result, mock_article)
        mock_objects.get.assert_called_once_with(pid_v3="pid123")

    @patch("article.models.Article.objects")
    def test_get_by_pid_v2(self, mock_objects):
        mock_article = Mock(spec=Article)
        mock_objects.get.return_value = mock_article

        result = Article.get(pid_v2="pid_v2_value")

        self.assertEqual(result, mock_article)
        mock_objects.get.assert_called_once_with(pid_v2="pid_v2_value")

    @patch("article.models.Article.objects")
    def test_get_by_sps_pkg_name(self, mock_objects):
        mock_article = Mock(spec=Article)
        mock_objects.get.return_value = mock_article

        result = Article.get(sps_pkg_name="pkg-v01")

        self.assertEqual(result, mock_article)
        mock_objects.get.assert_called_once_with(sps_pkg__sps_pkg_name="pkg-v01")

    @patch("article.models.Article.objects")
    def test_get_by_sps_pkg(self, mock_objects):
        mock_sps_pkg = Mock(spec=SPSPkg)
        mock_article = Mock(spec=Article)
        mock_objects.get.return_value = mock_article

        result = Article.get(sps_pkg=mock_sps_pkg)

        self.assertEqual(result, mock_article)
        mock_objects.get.assert_called_once_with(sps_pkg=mock_sps_pkg)

    @patch("article.models.Article.objects")
    def test_get_combines_multiple_params(self, mock_objects):
        mock_article = Mock(spec=Article)
        mock_objects.get.return_value = mock_article

        Article.get(pid_v2="v2", pid_v3="v3")

        mock_objects.get.assert_called_once_with(pid_v2="v2", pid_v3="v3")

    @patch("article.models.Article.objects")
    def test_get_raises_does_not_exist(self, mock_objects):
        mock_objects.get.side_effect = Article.DoesNotExist()

        with self.assertRaises(Article.DoesNotExist):
            Article.get(pid_v3="pid123")

    @patch("article.models.Article.objects")
    def test_get_propagates_multiple_objects_returned(self, mock_objects):
        """get() não trata duplicidade — quem chama decide o que fazer."""
        mock_objects.get.side_effect = Article.MultipleObjectsReturned()

        with self.assertRaises(Article.MultipleObjectsReturned):
            Article.get(pid_v3="pid123")


# ============================================================
# Article.delete_related_items()
# ============================================================


class ArticleDeleteRelatedItemsTestCase(unittest.TestCase):
    """Testes para Article.delete_related_items()."""

    @patch("article.models.ArticleWebPage")
    @patch("article.models.ArticleCollection")
    @patch("article.models.ArticleTitle")
    @patch("article.models.ArticleDOIWithLang")
    def test_deletes_all_related_and_the_queryset_itself(
        self, mock_doi, mock_title, mock_collection, mock_webpage
    ):
        mock_qs = MagicMock()
        mock_qs.delete.return_value = (3, {})

        result = Article.delete_related_items(mock_qs)

        mock_doi.objects.filter.assert_called_once_with(article__in=mock_qs)
        mock_doi.objects.filter.return_value.delete.assert_called_once()
        mock_title.objects.filter.assert_called_once_with(parent__in=mock_qs)
        mock_title.objects.filter.return_value.delete.assert_called_once()
        mock_collection.objects.filter.assert_called_once_with(article__in=mock_qs)
        mock_collection.objects.filter.return_value.delete.assert_called_once()
        mock_webpage.objects.filter.assert_called_once_with(article__in=mock_qs)
        mock_webpage.objects.filter.return_value.delete.assert_called_once()
        mock_qs.delete.assert_called_once()
        self.assertEqual(result, (3, {}))


# ============================================================
# Article.create_or_update()
# ============================================================


class ArticleCreateOrUpdateTestCase(unittest.TestCase):

    def setUp(self):
        patcher = patch.multiple(
            Article,
            add_journal=DEFAULT,
            add_issue=DEFAULT,
            add_pages=DEFAULT,
            add_article_publication_date=DEFAULT,
            add_pp_xml=DEFAULT,
            add_sections=DEFAULT,
            add_position=DEFAULT,
            add_article_titles=DEFAULT,
            add_doi_with_lang=DEFAULT,
            save=DEFAULT,
        )
        self.mocks = patcher.start()
        self.addCleanup(patcher.stop)

    def _make_sps_pkg(self, pid_v3="pidv3", pid_v2="pidv2"):
        mock_xml_with_pre = Mock()
        mock_xml_with_pre.xmltree.find.return_value.get.return_value = "research-article"

        # obj.sps_pkg = sps_pkg também é ForeignKey — precisa de _state fake.
        mock_sps_pkg = _mock_model_instance(
            SPSPkg,
            xml_with_pre=mock_xml_with_pre,
            pid_v3=pid_v3,
            pid_v2=pid_v2,
        )
        return mock_sps_pkg, mock_xml_with_pre

    def test_raises_value_error_without_sps_pkg(self):
        with self.assertRaises(ValueError):
            Article.create_or_update(_mock_model_instance(User), None)

    def test_raises_value_error_when_xml_with_pre_missing(self):
        mock_sps_pkg = _mock_model_instance(SPSPkg, xml_with_pre=None)

        with self.assertRaises(ValueError):
            Article.create_or_update(_mock_model_instance(User), mock_sps_pkg)

    @patch.object(Article, "get")
    def test_creates_new_article_when_does_not_exist(self, mock_get):
        mock_get.side_effect = Article.DoesNotExist()
        mock_sps_pkg, mock_xml_with_pre = self._make_sps_pkg()
        mock_user = _mock_model_instance(User)

        obj = Article.create_or_update(mock_user, mock_sps_pkg)

        self.assertEqual(obj.creator, mock_user)
        self.assertEqual(obj.sps_pkg, mock_sps_pkg)
        self.assertEqual(obj.pid_v3, mock_sps_pkg.pid_v3)
        self.assertEqual(obj.pid_v2, mock_sps_pkg.pid_v2)
        self.mocks["add_journal"].assert_called_once_with(mock_xml_with_pre)
        self.mocks["add_issue"].assert_called_once_with(mock_xml_with_pre)

    @patch.object(Article, "get")
    def test_add_sections_receives_xml_with_pre(self, mock_get):
        mock_get.side_effect = Article.DoesNotExist()
        mock_sps_pkg, mock_xml_with_pre = self._make_sps_pkg()
        mock_user = _mock_model_instance(User)

        Article.create_or_update(mock_user, mock_sps_pkg)

        self.mocks["add_sections"].assert_called_once_with(mock_user, mock_xml_with_pre)

    @patch.object(Article, "get")
    def test_add_position_runs_after_add_sections(self, mock_get):
        mock_get.side_effect = Article.DoesNotExist()
        mock_sps_pkg, mock_xml_with_pre = self._make_sps_pkg()
        mock_user = _mock_model_instance(User)

        manager = Mock()
        manager.attach_mock(self.mocks["add_sections"], "add_sections")
        manager.attach_mock(self.mocks["add_position"], "add_position")

        Article.create_or_update(mock_user, mock_sps_pkg, position=None)

        call_names = [c[0] for c in manager.mock_calls]
        self.assertLess(
            call_names.index("add_sections"), call_names.index("add_position")
        )

    @patch.object(Article, "delete_related_items")
    @patch.object(Article, "get")
    def test_deduplicates_on_multiple_objects_returned(
        self, mock_get, mock_delete_related
    ):
        mock_get.side_effect = Article.MultipleObjectsReturned()
        mock_sps_pkg, mock_xml_with_pre = self._make_sps_pkg()
        mock_user = _mock_model_instance(User)

        kept = Mock(spec=Article)
        kept.id = 1

        mock_qs = MagicMock()
        mock_qs.order_by.return_value = mock_qs
        mock_qs.first.return_value = kept
        mock_exclude_qs = MagicMock()
        mock_qs.exclude.return_value = mock_exclude_qs

        with patch("article.models.Article.objects") as mock_objects:
            mock_objects.filter.return_value = mock_qs
            result = Article.create_or_update(mock_user, mock_sps_pkg)

        self.assertEqual(result, kept)
        mock_qs.exclude.assert_called_once_with(id=1)
        mock_delete_related.assert_called_once_with(mock_exclude_qs)

    @patch.object(Article, "get")
    def test_uses_provided_journal_and_issue_instead_of_detecting_from_xml(
        self, mock_get
    ):
        mock_get.side_effect = Article.DoesNotExist()
        mock_sps_pkg, mock_xml_with_pre = self._make_sps_pkg()
        mock_user = _mock_model_instance(User)
        mock_journal = _mock_model_instance(Journal)
        mock_issue = _mock_model_instance(Issue)

        obj = Article.create_or_update(
            mock_user, mock_sps_pkg, issue=mock_issue, journal=mock_journal
        )

        self.assertEqual(obj.journal, mock_journal)
        self.assertEqual(obj.issue, mock_issue)
        self.mocks["add_journal"].assert_not_called()
        self.mocks["add_issue"].assert_not_called()


# ============================================================
# Article.get_repeated_values()
# ============================================================


class ArticleGetRepeatedValuesTestCase(unittest.TestCase):
    """Testes para Article.get_repeated_values()."""

    @patch("article.models.Article.objects")
    def test_uses_default_manager_when_no_queryset_given(self, mock_objects):
        mock_filtered = MagicMock()
        mock_objects.filter.return_value = mock_filtered
        mock_annotated = MagicMock()
        mock_filtered.values.return_value.annotate.return_value = mock_annotated
        mock_annotated.filter.return_value.values_list.return_value = ["v1", "v2"]

        result = Article.get_repeated_values("pid_v2")

        mock_objects.filter.assert_called_once_with()
        mock_filtered.values.assert_called_once_with("pid_v2")
        self.assertEqual(result, ["v1", "v2"])

    def test_uses_given_queryset(self):
        mock_qs = MagicMock()
        mock_filtered = MagicMock()
        mock_qs.filter.return_value = mock_filtered
        mock_annotated = MagicMock()
        mock_filtered.values.return_value.annotate.return_value = mock_annotated
        mock_annotated.filter.return_value.values_list.return_value = ["v1"]

        result = Article.get_repeated_values(
            "sps_pkg__sps_pkg_name", queryset=mock_qs
        )

        mock_qs.filter.assert_called_once_with()
        mock_filtered.values.assert_called_once_with("sps_pkg__sps_pkg_name")
        self.assertEqual(result, ["v1"])

    def test_filters_by_issue_when_given(self):
        mock_qs = MagicMock()
        mock_issue = Mock()
        mock_filtered = MagicMock()
        mock_qs.filter.return_value = mock_filtered
        mock_annotated = MagicMock()
        mock_filtered.values.return_value.annotate.return_value = mock_annotated
        mock_annotated.filter.return_value.values_list.return_value = []

        Article.get_repeated_values("pid_v2", queryset=mock_qs, issue=mock_issue)

        mock_qs.filter.assert_called_once_with(issue=mock_issue)


# ============================================================
# Article.exclude_invalid_records() / _exclude_invalid_records()
# ============================================================


class ArticleExcludeInvalidRecordsTestCase(unittest.TestCase):
    """Testes para o wrapper exclude_invalid_records()."""

    def test_wrapper_catches_exceptions(self):
        with patch.object(
            Article, "_exclude_invalid_records", side_effect=Exception("boom")
        ):
            result = Article.exclude_invalid_records(Mock(), Mock(), [1, 2])

        self.assertIn("error", result)
        self.assertEqual(result["error"], "boom")
        self.assertIn("traceback", result)

    def test_wrapper_returns_inner_result_on_success(self):
        expected = {"total_deleted_items": 0}
        with patch.object(
            Article, "_exclude_invalid_records", return_value=expected
        ):
            result = Article.exclude_invalid_records(Mock(), Mock(), [1, 2])

        self.assertEqual(result, expected)


class ArticleExcludeInvalidRecordsInternalTestCase(unittest.TestCase):

    @patch.object(Article, "delete_related_items", return_value=(1, {}))
    @patch("article.models.SPSPkg")
    @patch("article.models.PidProviderXML")
    @patch("article.models.Article.get_repeated_values")
    @patch("article.models.Article.objects")
    def test_response_dict_survives_duplicate_processing(
        self,
        mock_objects,
        mock_get_repeated,
        mock_pp_xml,
        mock_sps_pkg,
        mock_delete_related,
    ):
        user = Mock()
        issue = Mock()

        # 1) Passo de pid_v2 inválido: nada a fazer.
        step1_qs = MagicMock()
        step1_qs.filter.return_value = step1_qs
        step1_qs.exists.return_value = False

        # 2) Passo de pp_xml ausente: queryset vazio (sem itens a iterar).
        step2_qs = MagicMock()
        step2_qs.__iter__ = Mock(return_value=iter([]))

        # 3) Passo de duplicidade: só o primeiro field_name terá duplicados.
        dup_article = Mock()
        dup_article.pid_v2 = "dup-pid"
        dup_article.sps_pkg = Mock(sps_pkg_name="dup-pkg")
        dup_article.article_collections = MagicMock()
        dup_collection = Mock()
        dup_article.article_collections.all.return_value = [dup_collection]
        dup_article.create_or_update_article_collections = Mock()
        dup_article.check_availability = Mock()
        dup_article.available_on_public_website = Mock(return_value={"valid": True})

        keep_article = Mock()
        keep_article.id = 1
        keep_article.pk = 1

        duplicados_qs = MagicMock()
        duplicados_qs.order_by.return_value = duplicados_qs
        duplicados_qs.exists.return_value = True
        duplicados_qs.first.return_value = keep_article
        duplicados_qs.__iter__ = Mock(return_value=iter([dup_article]))

        remover_qs = MagicMock()
        remover_qs.exists.return_value = True
        remover_qs.values_list.return_value = [(None, "dup-pkg-2", 55)]
        duplicados_qs.exclude.return_value = remover_qs

        step3_qs = MagicMock()
        step3_qs.filter.return_value = duplicados_qs

        def select_related_side_effect(*args, **kwargs):
            if args == ("pp_xml", "sps_pkg"):
                m = MagicMock()
                m.filter.return_value = step1_qs
                return m
            if args == ("pp_xml",):
                m = MagicMock()
                m.filter.return_value = step2_qs
                return m
            if args == ("journal",):
                m = MagicMock()
                m.filter.return_value = step3_qs
                return m
            return MagicMock()

        mock_objects.select_related.side_effect = select_related_side_effect

        final_qs = MagicMock()
        final_qs.values_list.return_value = []
        mock_objects.filter.return_value = final_qs

        # Duplicados só na primeira passagem do field_name.
        mock_get_repeated.side_effect = [["dup-value"], []]

        result = Article._exclude_invalid_records(user, issue, sps_pkg_id_list=[1])

        # As chaves acumuladas antes do loop de duplicidade sobrevivem
        # (bug 4: response não foi sobrescrito por available_on_public_website).
        self.assertIn("sps_pkg_with_invalid_pid_v2", result)
        self.assertIn("ppxml_invalid", result)
        self.assertIn("total_deleted_items", result)

        # A chave dinâmica foi alimentada sem KeyError.
        self.assertIn("repeated_sps_pkg__sps_pkg_name", result)
        self.assertTrue(
            any(
                value == "dup-value"
                for value, _names in result["repeated_sps_pkg__sps_pkg_name"]
            )
        )

        # bug 2: article_collections precisa ser consultado via .all().
        dup_article.article_collections.all.assert_called_once()
        dup_article.available_on_public_website.assert_called_once_with(
            dup_collection.collection
        )


# ============================================================
# Article.fix_sps_pkg_names()
# ============================================================


class ArticleFixSpsPkgNamesTestCase(unittest.TestCase):

    def test_uses_default_manager_when_no_items_given(self):
        mock_item = Mock()
        mock_item.pid_v3 = "pid3"
        mock_item.pid_v2 = "pid2"
        mock_item.sps_pkg.sps_pkg_name = "pkg-v01"
        mock_item.fix_sps_pkg_name.return_value = "pkg-v02"
        mock_item.pp_xml.pkg_name = "old-name"
        mock_item.pp_xml.fix_pkg_name.return_value = "new-name"

        mock_filtered = MagicMock()
        mock_filtered.select_related.return_value.exclude.return_value = [mock_item]

        with patch("article.models.Article.objects") as mock_objects:
            mock_objects.filter.return_value = mock_filtered
            result = Article.fix_sps_pkg_names()

        mock_objects.filter.assert_called_once_with(
            sps_pkg__isnull=False, issue__supplement__isnull=False
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["pid_v3"], "pid3")
        self.assertEqual(result[0]["sps_pkg__pkg_name"], "pkg-v01")
        self.assertEqual(result[0]["sps_pkg__pkg_name_fixed"], "pkg-v02")
        self.assertEqual(result[0]["pp_xml__pkg_name"], "old-name")
        self.assertEqual(result[0]["pp_xml__pkg_name_fixed"], "new-name")

    def test_applies_filter_chain_to_given_items_not_the_original_queryset(self):
        """
        Regressão do bug 3: passando um `items` customizado, o loop deve
        iterar sobre o resultado FILTRADO (filter + select_related +
        exclude), e não sobre o `items` original sem filtro nenhum.
        """
        original_item = Mock()  # não deveria aparecer no resultado

        filtered_item = Mock()
        filtered_item.pid_v3 = "pid3-filtered"
        filtered_item.pid_v2 = "pid2-filtered"
        filtered_item.sps_pkg.sps_pkg_name = "pkg-filtered"
        filtered_item.fix_sps_pkg_name.return_value = "pkg-filtered-fixed"
        filtered_item.pp_xml.pkg_name = "old"
        filtered_item.pp_xml.fix_pkg_name.return_value = "new"

        mock_items = MagicMock()
        mock_items.__iter__ = Mock(return_value=iter([original_item]))
        mock_filtered = MagicMock()
        mock_items.filter.return_value = mock_filtered
        mock_filtered.select_related.return_value.exclude.return_value = [
            filtered_item
        ]

        result = Article.fix_sps_pkg_names(items=mock_items)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["pid_v3"], "pid3-filtered")
        mock_items.filter.assert_called_once_with(
            sps_pkg__isnull=False, issue__supplement__isnull=False
        )

    def test_fix_sps_pkg_name_returns_none_without_sps_pkg(self):
        article = Mock(spec=Article)
        article.sps_pkg = None

        result = Article.fix_sps_pkg_name(article)

        self.assertIsNone(result)

    def test_fix_sps_pkg_name_delegates_to_sps_pkg(self):
        article = Mock(spec=Article)
        article.sps_pkg = Mock()
        article.sps_pkg.fix_sps_pkg_name.return_value = "new-name"

        result = Article.fix_sps_pkg_name(article)

        article.sps_pkg.fix_sps_pkg_name.assert_called_once_with(save=True)
        self.assertEqual(result, "new-name")


if __name__ == "__main__":
    unittest.main()