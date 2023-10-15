from django.utils.translation import gettext_lazy as _

from migration.choices import XML_STATUS

ANNOTATION_COMMENT = "comment"
ANNOTATION_PKG_ERROR = "package-error"
ANNOTATION_WARNING = "warning"
ANNOTATION_EXECUTION_FAILURE = "execution-failure"


ANNOTATION_TYPES = [
    (ANNOTATION_COMMENT, _("comment")),
    (ANNOTATION_PKG_ERROR, _("package error")),
    (ANNOTATION_WARNING, _("warning")),
    (ANNOTATION_EXECUTION_FAILURE, _("execution failure")),
]


PKG_ORIGIN_MIGRATION = "MIGRATION"
PKG_ORIGIN_INGRESS_WITH_VALIDATION = "INGRESS_WITH_VALIDATION"
PKG_ORIGIN_INGRESS_WITHOUT_VALIDATION = "INGRESS_WITHOUT_VALIDATION"


PKG_ORIGIN = [
    (PKG_ORIGIN_MIGRATION, _("MIGRATION")),
    (PKG_ORIGIN_INGRESS_WITH_VALIDATION, _("INGRESS_WITH_VALIDATION")),
    (PKG_ORIGIN_INGRESS_WITHOUT_VALIDATION, _("INGRESS_WITHOUT_VALIDATION")),
]


PKG_ASSETS_STATUS_MISSING = "MISSING_ASSETS"
PKG_ASSETS_STATUS_COMPLETE = "COMPLETE"

PKG_ASSETS_STATUS = [
    (PKG_ASSETS_STATUS_MISSING, _("missing assets")),
    (PKG_ASSETS_STATUS_COMPLETE, _("pacote completo")),
]

PKG_XML_STATUS = XML_STATUS