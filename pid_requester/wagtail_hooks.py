from django.http import HttpResponseRedirect
from django.utils.translation import gettext as _
from wagtail.contrib.modeladmin.options import (
    ModelAdmin,
    ModelAdminGroup,
    modeladmin_register,
)
from wagtail.contrib.modeladmin.views import CreateView

from config.menu import get_menu_order
from .models import PidRequesterBadRequest, PidProviderConfig


class PidRequesterBadRequestCreateView(CreateView):
    def form_valid(self, form):
        self.object = form.save_all(self.request.user)
        return HttpResponseRedirect(self.get_success_url())


class PidRequesterBadRequestAdmin(ModelAdmin):
    model = PidRequesterBadRequest
    inspect_view_enabled = True
    menu_label = _("PidRequesterBadRequests")
    create_view_class = PidRequesterBadRequestCreateView
    menu_icon = "folder"
    menu_order = 300
    add_to_settings_menu = False
    exclude_from_explorer = False

    list_display = (
        "basename",
        "error_type",
        "error_message",
    )
    list_filter = (
        "creator",
        "error_type",
    )
    search_fields = (
        "basename",
        "error_message",
    )


class PidProviderConfigCreateView(CreateView):
    def form_valid(self, form):
        self.object = form.save_all(self.request.user)
        return HttpResponseRedirect(self.get_success_url())


class PidProviderAdmin(ModelAdmin):
    model = PidProviderConfig
    inspect_view_enabled = True
    menu_label = _("Pid Provider Configuration")
    create_view_class = PidProviderConfigCreateView
    menu_icon = "folder"
    menu_order = 300
    add_to_settings_menu = False
    exclude_from_explorer = False

    list_display = (
        "pid_provider_api_post_xml",
        "pid_provider_api_get_token",
        "api_username",
        "api_password",
        "timeout",
    )


class PidProviderAdminGroup(ModelAdminGroup):
    menu_label = _("Pid Provider")
    menu_icon = "folder-open-inverse"
    menu_order = get_menu_order("pid-provider")
    items = (
        PidProviderAdmin,
        PidRequesterBadRequestAdmin,
    )


modeladmin_register(PidProviderAdminGroup)
