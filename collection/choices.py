from django.utils.translation import gettext_lazy as _

CURRENT = 'C'

JOURNAL_PUBLICATION_STATUS = [
    (CURRENT, _('Current')),
]


QA = 'QA'
PUBLIC = 'PUBLIC'

WEBSITE_KIND = [
    (QA, _('QA')),
    (PUBLIC, _('PUBLIC')),
]