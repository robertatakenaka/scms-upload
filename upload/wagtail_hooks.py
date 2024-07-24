import json

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import include, path
from django.utils.translation import gettext as _
from wagtail import hooks
from wagtail.contrib.modeladmin.options import (
    ModelAdmin,
    ModelAdminGroup,
    modeladmin_register,
)

from config.menu import get_menu_order
from upload.views import (
    PackageAdminInspectView,
    PackageCreateView,
    QAPackageEditView,
    XMLInfoReportEditView,
    XMLErrorReportEditView,
    ValidationReportEditView,
    ApprovedPackageEditView,
)

from .button_helper import UploadButtonHelper
from .models import (
    Package,
    PkgValidationResult,
    QAPackage,
    ValidationReport,
    XMLError,
    XMLErrorReport,
    XMLInfo,
    XMLInfoReport,
    choices,
    ApprovedPackage,
)
from .permission_helper import UploadPermissionHelper


class PackageAdmin(ModelAdmin):
    model = Package
    button_helper_class = UploadButtonHelper
    permission_helper_class = UploadPermissionHelper
    create_view_class = PackageCreateView
    inspect_view_enabled = True
    inspect_view_class = PackageAdminInspectView
    menu_label = _("Packages")
    menu_icon = "folder"
    menu_order = 200
    add_to_settings_menu = False
    exclude_from_explorer = False
    list_per_page = 20

    list_display = (
        "file",
        "blocking_errors",
        "xml_errors_percentage",
        "xml_warnings_percentage",
        "category",
        "status",
        "creator",
        "updated",
        "expiration_date",
    )
    list_filter = (
        "category",
        "status",
    )
    search_fields = (
        "file",
        "issue__officialjournal__title",
        "article__pid_v3",
        "creator__username",
        "updated_by__username",
    )
    inspect_view_fields = (
        "article",
        "issue",
        "category",
        "status",
        "file",
        "created",
        "updated",
        "expiration_date",
        "files_list",
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        if self.permission_helper.user_can_access_all_packages(request.user, None):
            return qs

        return qs.filter(creator=request.user)


class QualityAnalysisPackageAdmin(ModelAdmin):
    model = QAPackage
    button_helper_class = UploadButtonHelper
    permission_helper_class = UploadPermissionHelper
    menu_label = _("Quality analysis")
    menu_icon = "folder"
    menu_order = 200
    edit_view_class = QAPackageEditView
    inspect_view_enabled = True
    inspect_view_class = PackageAdminInspectView
    inspect_template_name = "modeladmin/upload/package/inspect.html"
    add_to_settings_menu = False
    exclude_from_explorer = False
    list_per_page = 20

    list_display = (
        "file",
        "assignee",
        "analyst",
        "xml_errors_percentage",
        "xml_warnings_percentage",
        "contested_xml_errors_percentage",
        "declared_impossible_to_fix_percentage",
        "category",
        "status",
        "updated",
        "expiration_date",
    )
    list_filter = ("status", "category")
    search_fields = (
        "file",
        "assignee__username",
        "analyst__user__username",
        "creator__username",
        "updated_by__username",
        "assignee__email",
        "analyst__user__email",
        "creator__email",
        "updated_by__email",
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        if self.permission_helper.user_can_access_all_packages(request.user, None):
            return qs.filter(
                status__in=[
                    choices.PS_PENDING_QA_DECISION,
                    choices.PS_VALIDATED_WITH_ERRORS,
                    # choices.PS_APPROVED_WITH_ERRORS,
                    choices.PS_REJECTED,
                ]
            )

        return qs.none()


class ApprovedPackageAdmin(ModelAdmin):
    model = ApprovedPackage

    button_helper_class = UploadButtonHelper
    permission_helper_class = UploadPermissionHelper
    menu_label = _("Approved package")
    menu_icon = "folder"
    menu_order = 200
    edit_view_class = ApprovedPackageEditView
    inspect_view_enabled = True
    inspect_view_class = PackageAdminInspectView
    inspect_template_name = "modeladmin/upload/package/inspect.html"
    add_to_settings_menu = False
    exclude_from_explorer = False
    list_per_page = 20

    list_display = (
        "file",
        "assignee",
        "analyst",
        "toc_sections",
        "order",
        "website_pub_date",
        "category",
        "status",
        "updated",
    )
    list_filter = ("status", "category")
    search_fields = (
        "file",
        "assignee__username",
        "analyst__user__username",
        "creator__username",
        "updated_by__username",
        "assignee__email",
        "analyst__user__email",
        "creator__email",
        "updated_by__email",
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        if self.permission_helper.user_can_access_all_packages(request.user, None):
            return qs.filter(
                status__in=[
                    choices.PS_APPROVED,
                    choices.PS_APPROVED_WITH_ERRORS,
                    choices.PS_PREPARE_SPSPKG,
                    choices.PS_PREPARE_PUBLICATION,
                    choices.PS_READY_TO_QA_WEBSITE,
                    choices.PS_READY_TO_PUBLISH,
                    choices.PS_SCHEDULED_PUBLICATION,
                    choices.PS_PUBLISHED,
                ]
            )

        return qs.none()


class XMLErrorReportAdmin(ModelAdmin):
    model = XMLErrorReport
    permission_helper_class = UploadPermissionHelper
    edit_view_class = XMLErrorReportEditView

    # create_view_class = XMLErrorReportCreateView
    inspect_view_enabled = True
    # inspect_view_class = XMLErrorReportAdminInspectView
    menu_label = _("XML Error Reports")
    menu_icon = "error"
    add_to_settings_menu = False
    exclude_from_explorer = False
    list_display = (
        "package",
        "category",
        "title",
        "creation",
    )
    list_filter = (
        "category",
        "creation",
    )
    search_fields = (
        "title",
        "package__name",
        "package__file",
    )

    def get_queryset(self, request):
        if (
            request.user.is_superuser
            or self.permission_helper.user_can_access_all_packages(request.user, None)
        ):
            return super().get_queryset(request)

        return super().get_queryset(request).filter(package__creator=request.user)


class XMLErrorAdmin(ModelAdmin):
    model = XMLError
    permission_helper_class = UploadPermissionHelper
    # create_view_class = XMLErrorCreateView
    inspect_view_enabled = True
    # inspect_view_class = XMLErrorAdminInspectView
    menu_label = _("XML errors")
    menu_icon = "error"
    add_to_settings_menu = False
    exclude_from_explorer = False
    list_display = (
        "subject",
        "attribute",
        "focus",
        "message",
        "report",
    )
    list_filter = (
        "validation_type",
        "parent",
        "parent_id",
        "subject",
        "attribute",
    )
    search_fields = (
        "focus",
        "message",
        "advice",
        "package__name",
        "package__file",
    )

    def get_queryset(self, request):
        if (
            request.user.is_superuser
            or self.permission_helper.user_can_access_all_packages(request.user, None)
        ):
            return super().get_queryset(request)

        return super().get_queryset(request).filter(package__creator=request.user)


class XMLInfoReportAdmin(ModelAdmin):
    model = XMLInfoReport
    permission_helper_class = UploadPermissionHelper
    edit_view_class = XMLInfoReportEditView
    # create_view_class = XMLInfoReportCreateView
    inspect_view_enabled = True
    # inspect_view_class = XMLInfoReportAdminInspectView
    menu_label = _("XML Info Reports")
    menu_icon = "error"
    add_to_settings_menu = False
    exclude_from_explorer = False
    list_display = (
        "package",
        "category",
        "title",
        "creation",
    )
    list_filter = (
        "category",
        "creation",
    )
    search_fields = (
        "title",
        "package__name",
        "package__file",
    )

    def get_queryset(self, request):
        if (
            request.user.is_superuser
            or self.permission_helper.user_can_access_all_packages(request.user, None)
        ):
            return super().get_queryset(request)

        return super().get_queryset(request).filter(package__creator=request.user)


class XMLInfoAdmin(ModelAdmin):
    model = XMLInfo
    permission_helper_class = UploadPermissionHelper
    # create_view_class = XMLInfoCreateView
    inspect_view_enabled = True
    # inspect_view_class = XMLInfoAdminInspectView
    menu_label = _("XML info")
    menu_icon = "error"
    add_to_settings_menu = False
    exclude_from_explorer = False
    list_display = (
        "subject",
        "attribute",
        "focus",
        "message",
        "report",
    )
    list_filter = (
        "status",
        "validation_type",
        "parent",
        "parent_id",
        "subject",
        "attribute",
    )
    search_fields = (
        "focus",
        "message",
        "package__name",
        "package__file",
    )

    def get_queryset(self, request):
        if (
            request.user.is_superuser
            or self.permission_helper.user_can_access_all_packages(request.user, None)
        ):
            return super().get_queryset(request)

        return super().get_queryset(request).filter(package__creator=request.user)


class ValidationReportAdmin(ModelAdmin):
    model = ValidationReport
    permission_helper_class = UploadPermissionHelper
    # create_view_class = ValidationReportCreateView
    edit_view_class = ValidationReportEditView

    inspect_view_enabled = True
    # inspect_view_class = ValidationReportAdminInspectView
    menu_label = _("Validation Reports")
    menu_icon = "error"
    add_to_settings_menu = False
    exclude_from_explorer = False
    list_display = (
        "package",
        "category",
        "title",
        "creation",
    )
    list_filter = (
        "category",
        "creation",
    )
    search_fields = (
        "title",
        "package__name",
        "package__file",
    )

    def get_queryset(self, request):
        if (
            request.user.is_superuser
            or self.permission_helper.user_can_access_all_packages(request.user, None)
        ):
            return super().get_queryset(request)

        return super().get_queryset(request).filter(package__creator=request.user)


class ValidationAdmin(ModelAdmin):
    model = PkgValidationResult
    permission_helper_class = UploadPermissionHelper
    # create_view_class = ValidationCreateView
    inspect_view_enabled = True
    # inspect_view_class = ValidationAdminInspectView
    menu_label = _("Validations")
    menu_icon = "error"
    add_to_settings_menu = False
    exclude_from_explorer = False
    list_display = (
        "subject",
        "status",
        "message",
        "created",
    )
    list_filter = (
        "status",
    )
    search_fields = (
        "subject",
        "status",
        "message",
    )

    def get_queryset(self, request):
        if (
            request.user.is_superuser
            or self.permission_helper.user_can_access_all_packages(request.user, None)
        ):
            return super().get_queryset(request)

        return super().get_queryset(request).filter(package__creator=request.user)


class UploadModelAdminGroup(ModelAdminGroup):
    menu_icon = "folder"
    menu_label = "Upload"
    items = (
        PackageAdmin,
        QualityAnalysisPackageAdmin,
        ApprovedPackageAdmin,
    )
    menu_order = get_menu_order("upload")


modeladmin_register(UploadModelAdminGroup)


class UploadReportsModelAdminGroup(ModelAdminGroup):
    menu_icon = "folder"
    menu_label = _("Package errors")
    items = (
        # os itens a seguir possibilitam que na página Package.inspect
        # funcionem os links para os relatórios
        XMLErrorAdmin,
        XMLErrorReportAdmin,
        XMLInfoReportAdmin,
        ValidationAdmin,
        ValidationReportAdmin
    )
    menu_order = get_menu_order("upload")


modeladmin_register(UploadReportsModelAdminGroup)


@hooks.register("register_admin_urls")
def register_disclosure_url():
    return [
        path("upload/", include("upload.urls", namespace="upload")),
    ]
