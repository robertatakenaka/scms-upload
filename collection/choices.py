from django.utils.translation import gettext_lazy as _

# JOURNAL_PUBLICATION_STATUS
# Embora alguns periódicos estão encerrados (CEASED) ou suspensos (SUSPENDED),
# eles ainda ficam disponíveis no site (`JOURNAL_AT_WEBSITE_STATUS = CURRENT`)
CURRENT = "C"
NOT_INFORMED = ""
CEASED = "D"
UNKNOWN = "?"
SUSPENDED = "S"

JOURNAL_PUBLICATION_STATUS = [
    (SUSPENDED, _("Suspended")),
    (UNKNOWN, _("Unknown")),
    (CEASED, _("Ceased")),
    (NOT_INFORMED, _("Not informed")),
    (CURRENT, _("Current")),
]


# AVAILABILTY on the website
JOURNAL_AVAILABILTY_STATUS = [
    (UNKNOWN, _("Unknown")),
    (CURRENT, _("Current")),
]


QA = "QA"
PUBLIC = "PUBLIC"

WEBSITE_KIND = [
    (QA, _("QA")),
    (PUBLIC, _("PUBLIC")),
]

COLLECTION_TEAM = "collection"
JOURNAL_EDITORIAL_TEAM = "journal"
XML_PRODUCTION_TEAM = "xml"

TEAM_TYPES = [
    (XML_PRODUCTION_TEAM, _("XML production team")),
    (JOURNAL_EDITORIAL_TEAM, _("editorial team")),
    (COLLECTION_TEAM, _("collection team")),
]


QA = "qa"
MANAGEMENT = "management"
XML_PRODUCTION = "xml"

TEAM_ROLES = [
    (XML_PRODUCTION, _("XML production")),
    (MANAGEMENT, _("editorial management")),
    (QA, _("quality assurance")),
]
