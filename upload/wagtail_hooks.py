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
from wagtail.contrib.modeladmin.views import CreateView, InspectView

from article.models import Article
from config.menu import get_menu_order
from issue.models import Issue
from upload.utils import file_utils
from upload.utils.xml_utils import XMLFormatError

from .button_helper import UploadButtonHelper
from .models import (
    ErrorResolutionOpinion,
    Package,
    QAPackage,
    ValidationResult,
    ValidationReport,
    choices,
    XMLError,
    XMLErrorReport,
    XMLInfo,
    XMLInfoReport,
    ErrorNegativeReactionDecision,
)
from .permission_helper import UploadPermissionHelper
from .controller import receive_package
from .utils import package_utils
from upload.tasks import task_validate_original_zip_file


class PackageCreateView(CreateView):
    def form_valid(self, form):

        package = form.save_all(self.request.user)

        response = receive_package(package)

        if response.get("error_type") == choices.VE_PACKAGE_FILE_ERROR:
            # error no arquivo
            messages.error(self.request, response.get("error"))
            return HttpResponseRedirect(self.request.META["HTTP_REFERER"])

        if response.get("error"):
            # error
            messages.error(self.request, response.get("error"))
            return redirect(f"/admin/upload/package/inspect/{package.id}")

        messages.success(
            self.request,
            _("Package has been successfully submitted and will be analyzed"),
        )

        # dispara a tarefa que realiza as validações de
        # assets, renditions, XML content etc

        try:
            journal_id = response["journal"].id
        except (KeyError, AttributeError):
            journal_id = None
        try:
            issue_id = response["issue"].id
        except (KeyError, AttributeError):
            issue_id = None

        task_validate_original_zip_file.apply_async(
            kwargs=dict(
                package_id=package.id,
                file_path=package.file.path,
                journal_id=journal_id,
                issue_id=issue_id,
                article_id=package.article and package.article.id or None,
            )
        )
        return HttpResponseRedirect(self.get_success_url())


class PackageAdminInspectView(InspectView):
    def get_optimized_package_filepath_and_directory(self):
        # Obtém caminho do pacote otimizado
        _path = package_utils.generate_filepath_with_new_extension(
            self.instance.file.name,
            ".optz",
            True,
        )

        # Obtém diretório em que o pacote otimizado foi extraído
        _directory = file_utils.get_file_url(
            dirname="", filename=file_utils.get_filename_from_filepath(_path)
        )

        return _path, _directory

    def set_pdf_paths(self, data, optz_dir):
        try:
            for rendition in package_utils.get_article_renditions_from_zipped_xml(
                self.instance.file.name
            ):
                package_files = file_utils.get_file_list_from_zip(
                    self.instance.file.name
                )
                document_name = package_utils.get_xml_filename(package_files)
                rendition_name = package_utils.get_rendition_expected_name(
                    rendition, document_name
                )
                data["pdfs"].append(
                    {
                        "base_uri": file_utils.os.path.join(optz_dir, rendition_name),
                        "language": rendition.language,
                    }
                )
        except XMLFormatError:
            data["pdfs"] = []

    def get_context_data(self):
        data = {
            "validation_results": {},
            "package_id": self.instance.id,
            "original_pkg": self.instance.file.name,
            "status": self.instance.status,
            "category": self.instance.category,
            "languages": package_utils.get_languages(self.instance.file.name),
            "pdfs": [],
            "reports": list(self.instance.reports),
            "xml_error_reports": list(self.instance.xml_error_reports),
            "xml_info_reports": list(self.instance.xml_info_reports),
            "justified_errors": list(self.instance.justified_errors),
        }

        optz_file_path, optz_dir = self.get_optimized_package_filepath_and_directory()
        data["optimized_pkg"] = optz_file_path
        self.set_pdf_paths(data, optz_dir)

        for vr in self.instance.validationresult_set.all():
            vr_name = vr.report_name()
            if vr_name not in data["validation_results"]:
                data["validation_results"][vr_name] = {"status": vr.status}

            if vr.status == choices.VS_DISAPPROVED:
                if data["validation_results"][vr_name] != choices.VS_DISAPPROVED:
                    data["validation_results"][vr_name].update({"status": vr.status})

                if hasattr(vr, "analysis"):
                    data["validation_results"]["qa"] = self.instance.status

            if vr_name == choices.VR_XML_OR_DTD:
                if "xmls" not in data["validation_results"][vr_name]:
                    data["validation_results"][vr_name]["xmls"] = []

                if vr.data and isinstance(vr.data, dict):
                    data["validation_results"][vr_name]["xmls"].append(
                        {
                            "xml_name": vr.data.get("xml_path"),
                            "base_uri": file_utils.os.path.join(
                                optz_dir, vr.data.get("xml_path")
                            ),
                            "inspect_uri": ValidationResultAdmin().url_helper.get_action_url(
                                "inspect", vr.id
                            ),
                        }
                    )

        return super().get_context_data(**data)


class ValidationResultCreateView(CreateView):
    def get_instance(self):
        vr_object = super().get_instance()

        status = self.request.GET.get("status")
        if status and status in (choices.VS_APPROVED, choices.VS_DISAPPROVED):
            vr_object.status = status

        pkg_id = self.request.GET.get("package_id")
        if pkg_id:
            try:
                vr_object.package = Package.objects.get(pk=pkg_id)
            except Package.DoesNotExist:
                ...

        return vr_object

    def form_valid(self, form):
        self.object = form.save_all(self.request.user)

        op = ErrorResolutionOpinion()
        op.creator = self.request.user
        op.opinion = choices.ER_OPINION_FIX_DEMANDED
        op.validation_result_id = self.object.id
        op.package_id = self.object.package_id
        op.guidance = _("This error was reported by an user.")
        op.save()

        self.object.validation_result_opinion = op
        self.object.save()

        return HttpResponseRedirect(self.get_success_url())


class ValidationResultAdminInspectView(InspectView):
    def get_context_data(self):
        try:
            data = self.instance.data.copy()
        except AttributeError:
            data = {}
        data[
            "package_url"
        ] = f"/admin/upload/package/inspect/{self.instance.package.id}"
        return super().get_context_data(**data)


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

    list_display = (
        "file",
        "validations",
        "errors",
        "blocking_errors",
        "percentual",
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


class ValidationResultAdmin(ModelAdmin):
    model = ValidationResult
    permission_helper_class = UploadPermissionHelper
    create_view_class = ValidationResultCreateView
    inspect_view_enabled = True
    inspect_view_class = ValidationResultAdminInspectView
    menu_label = _("Validation results")
    menu_icon = "error"
    menu_order = 200
    add_to_settings_menu = False
    exclude_from_explorer = False
    list_display = (
        "report_name",
        "category",
        "status",
        "package",
        "message",
    )
    list_filter = (
        "category",
        "status",
    )
    search_fields = (
        "message",
        "package__name",
        "package__file",
    )
    inspect_view_fields = {
        "package",
        "category",
        "message",
        "data",
        "status",
    }

    def get_queryset(self, request):
        if (
            request.user.is_superuser
            or self.permission_helper.user_can_access_all_packages(request.user, None)
        ):
            return super().get_queryset(request)

        return super().get_queryset(request).filter(package__creator=request.user)


class QualityAnalysisPackageAdmin(ModelAdmin):
    model = QAPackage
    button_helper_class = UploadButtonHelper
    permission_helper_class = UploadPermissionHelper
    menu_label = _("Quality analysis")
    menu_icon = "folder"
    menu_order = 200
    inspect_view_enabled = True
    inspect_view_class = PackageAdminInspectView
    inspect_template_name = "modeladmin/upload/package/inspect.html"
    add_to_settings_menu = False
    exclude_from_explorer = False

    list_display = (
        "file",
        "assignee",
        "validations",
        "errors",
        "blocking_errors",
        "percentual",
        "category",
        "status",
        "updated",
        "expiration_date",
    )
    list_filter = ("assignee", "status", "category")
    search_fields = (
        "file",
        "assignee__username",
        "creator__username",
        "updated_by__username",
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        if self.permission_helper.user_can_access_all_packages(request.user, None):
            return qs.filter(status__in=[choices.PS_QA, choices.PS_VALIDATED_WITH_ERRORS])

        return qs.none()


class ValidationReportAdmin(ModelAdmin):
    model = ValidationReport
    permission_helper_class = UploadPermissionHelper
    # create_view_class = ValidationReportCreateView
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
        "conclusion",
    )
    list_filter = (
        "category",
        "conclusion",
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


class XMLErrorReportAdmin(ModelAdmin):
    model = XMLErrorReport
    permission_helper_class = UploadPermissionHelper
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
        "conclusion",
    )
    list_filter = (
        "category",
        "conclusion",
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
        "advice",
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


class ErrorNegativeReactionDecisionAdmin(ModelAdmin):
    model = ErrorNegativeReactionDecision
    permission_helper_class = UploadPermissionHelper
    menu_label = _("Quality analysis decision")
    menu_icon = "folder"
    add_to_settings_menu = False
    exclude_from_explorer = False
    list_display = (
        "error",
        "creator",
        "created",
        "updated_by",
        "updated",
    )
    list_filter = (
        "decision",
    )
    search_fields = (
        "error__message",
        "error__advice",
    )

    def get_queryset(self, request):
        if (
            request.user.is_superuser
            or self.permission_helper.user_can_analyse_error_validation_resolution(request.user, None)
        ):
            return super().get_queryset(request)

        return super().get_queryset(request).filter(package__creator=request.user)


class XMLInfoReportAdmin(ModelAdmin):
    model = XMLInfoReport
    permission_helper_class = UploadPermissionHelper
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
        "conclusion",
    )
    list_filter = (
        "category",
        "conclusion",
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


class UploadModelAdminGroup(ModelAdminGroup):
    menu_icon = "folder"
    menu_label = "Upload"
    items = (
        PackageAdmin,
        QualityAnalysisPackageAdmin,
        XMLErrorAdmin,

        # ValidationResultAdmin é necessário para apresentar 'inspect' de Package
        ValidationResultAdmin,
    )
    menu_order = get_menu_order("upload")


modeladmin_register(UploadModelAdminGroup)


class UploadReportsModelAdminGroup(ModelAdminGroup):
    menu_icon = "folder"
    menu_label = _("Upload reports")
    items = (

        # os itens a seguir possibilitam que na página Package.inspect
        # funcionem os links para os relatórios
        ValidationReportAdmin,
        XMLErrorReportAdmin,
        XMLInfoReportAdmin,
        ErrorNegativeReactionDecisionAdmin,
    )
    menu_order = get_menu_order("upload")

modeladmin_register(UploadReportsModelAdminGroup)


@hooks.register("register_admin_urls")
def register_disclosure_url():
    return [
        path("upload/", include("upload.urls", namespace="upload")),
    ]
