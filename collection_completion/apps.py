from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CollectionCompletionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "collection_completion"
    verbose_name = _("Collection completion")
