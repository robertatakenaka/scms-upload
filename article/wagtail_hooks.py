from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import include, path
from django.utils.translation import gettext as _
from wagtail import hooks
from wagtail.contrib.modeladmin.options import (
    ModelAdmin,
    ModelAdminGroup,
    modeladmin_register,
)

from config.menu import get_menu_order

from article.views import (
    ArticleCreateView,
    ArticleAdminInspectView,
    RequestArticleChangeCreateView,
    RelatedItemCreateView,
    ApprovedArticleEditView,
    TOCEditView,
)
from .button_helper import ArticleButtonHelper, RequestArticleChangeButtonHelper
from .models import Article, RelatedItem, RequestArticleChange, choices, ApprovedArticle, TOC
from .permission_helper import ArticlePermissionHelper

# from upload import exceptions as upload_exceptions
# from upload.models import Package
# from upload.tasks import get_or_create_package


class ArticleModelAdmin(ModelAdmin):
    model = Article
    menu_label = _("Articles")
    create_view_class = ArticleCreateView
    button_helper_class = ArticleButtonHelper
    permission_helper_class = ArticlePermissionHelper
    inspect_view_enabled = True
    inspect_view_class = ArticleAdminInspectView
    menu_icon = "doc-full"
    menu_order = get_menu_order("article")
    add_to_settings_menu = False
    exclude_from_explorer = False

    list_display = (
        "sps_pkg",
        "status",
        "issue",
        "journal",
        "created",
        "updated",
        # "updated_by",
    )
    list_filter = ("status",)
    search_fields = (
        "sps_pkg__sps_pkg_name",
        "pid_v3",
        "issue__publication_year",
    )
    inspect_view_fields = (
        "created",
        "updated",
        "creator",
        "updated_by",
        "pid_v3",
        # "pid_v2",
        # "aop_pid",
        "doi_with_lang",
        "article_type",
        "status",
        "issue",
        # "author",
        # "title_with_lang",
        "elocation_id",
        "fpage",
        "lpage",
    )


class ApprovedArticleModelAdmin(ModelAdmin):
    model = ApprovedArticle
    menu_label = _("Articles")
    edit_view_class = ApprovedArticleEditView
    button_helper_class = ArticleButtonHelper
    permission_helper_class = ArticlePermissionHelper
    inspect_view_enabled = False
    menu_icon = "doc-full"
    menu_order = get_menu_order("article")
    add_to_settings_menu = False
    exclude_from_explorer = False

    list_display = (
        "sps_pkg",
        "website_publication_date",
        "position",
        "status",
        "issue",
        "journal",
        "created",
        "updated",
        # "updated_by",
    )
    list_filter = ("status",)
    search_fields = (
        "sps_pkg__sps_pkg_name",
        "pid_v3",
        "issue__publication_year",
    )
    inspect_view_fields = (
        "created",
        "updated",
        "creator",
        "updated_by",
        "pid_v3",
        # "pid_v2",
        # "aop_pid",
        "doi_with_lang",
        "article_type",
        "status",
        "issue",
        # "author",
        # "title_with_lang",
        "elocation_id",
        "fpage",
        "lpage",
    )


class TOCModelAdmin(ModelAdmin):
    model = TOC
    menu_label = _("Table of contents")
    edit_view_class = TOCEditView
    # button_helper_class = ArticleButtonHelper
    # permission_helper_class = ArticlePermissionHelper
    inspect_view_enabled = False
    menu_icon = "doc-full"
    menu_order = get_menu_order("article")
    add_to_settings_menu = False
    exclude_from_explorer = False

    list_display = (
        "issue",
        "main_section",
        "created",
        "updated",
    )
    search_fields = (
        "issue__journal__title",
        "issue__publication_year",
        "issue__volume",
        "issue__number",
        "issue__supplement",
        "main_section__plain_text",
        "translated_sections__plain_text",
    )


class RelatedItemModelAdmin(ModelAdmin):
    model = RelatedItem
    menu_label = _("Related items")
    create_view_class = RelatedItemCreateView
    inspect_view_enabled = True
    menu_icon = "doc-full"
    menu_order = 200
    add_to_settings_menu = False
    exclude_from_explorer = False

    list_display = (
        "item_type",
        "source_article",
        "target_article",
        "created",
        "updated",
        "updated_by",
    )
    list_filter = (
        "item_type",
        "target_article__issue",
    )
    search_fields = ("target_article__issue__journal_ISSNL",)
    inspect_view_fields = (
        "created",
        "updated",
        "creator",
        "updated_by",
        "item_type",
        "source_article",
        "target_article",
    )


class RequestArticleChangeModelAdmin(ModelAdmin):
    model = RequestArticleChange
    menu_label = _("Changes request")
    button_helper_class = RequestArticleChangeButtonHelper
    create_view_class = RequestArticleChangeCreateView
    permission_helper_class = ArticlePermissionHelper
    menu_icon = "doc-full"
    menu_order = 200
    add_to_settings_menu = False
    exclude_from_explorer = False

    list_display = (
        "creator",
        "created",
        "deadline",
        "article",
        "pid_v3",
        "change_type",
        "demanded_user",
    )
    list_filter = ("change_type",)
    search_fields = (
        "article__pid_v2",
        "article__pid_v3",
        "article__doi_with_lang__doi",
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        if self.permission_helper.user_can_make_article_change(request.user, None):
            return qs.filter(demanded_user=request.user)

        return qs


class ArticleModelAdminGroup(ModelAdminGroup):
    menu_label = _("Articles")
    menu_icon = "folder-open-inverse"
    # menu_order = get_menu_order("article")
    menu_order = 400
    items = (
        ArticleModelAdmin,
        # RelatedItemModelAdmin,
        # RequestArticleChangeModelAdmin,
        ApprovedArticleModelAdmin,
    )


# modeladmin_register(ArticleModelAdminGroup)
modeladmin_register(ArticleModelAdmin)


@hooks.register("register_admin_urls")
def register_disclosure_url():
    return [
        path("article/", include("article.urls", namespace="article")),
    ]
