from django.urls import include, path, reverse
from django.utils.translation import gettext_lazy as _
from wagtail import hooks
from wagtail.admin.menu import MenuItem


class AdminOnlyMenuItem(MenuItem):
    def is_shown(self, request):
        return request.user.is_superuser


@hooks.register("register_admin_urls")
def register_collection_completion_urls():
    return [
        path(
            "collection_completion/",
            include("collection_completion.urls", namespace="collection_completion"),
        ),
    ]


@hooks.register("register_admin_menu_item")
def register_collection_completion_menu_item():
    return AdminOnlyMenuItem(
        _("Collection completion"),
        reverse("collection_completion:list"),
        name="collection_completion",
        icon_name="list-ul",
        order=10000,
    )
