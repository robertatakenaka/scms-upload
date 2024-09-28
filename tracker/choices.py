from django.utils.translation import gettext_lazy as _

ERROR = "ERROR"
EXCEPTION = "EXCEPTION"
INFO = "INFO"
WARNING = "WARNING"

EVENT_MSG_TYPE = [
    (ERROR, _("error")),
    (WARNING, _("warning")),
    (INFO, _("info")),
    (EXCEPTION, _("exception")),
]


PROGRESS_STATUS_IGNORED = "IGNORED"
PROGRESS_STATUS_REPROC = "REPROC"
PROGRESS_STATUS_TODO = "TODO"
PROGRESS_STATUS_DOING = "DOING"
PROGRESS_STATUS_DONE = "DONE"
PROGRESS_STATUS_PENDING = "PENDING"
PROGRESS_STATUS_BLOCKED = "BLOCKED"

PROGRESS_STATUS = (
    (PROGRESS_STATUS_REPROC, _("To reprocess")),
    (PROGRESS_STATUS_TODO, _("To do")),
    (PROGRESS_STATUS_DONE, _("Done")),
    (PROGRESS_STATUS_DOING, _("Doing")),
    (PROGRESS_STATUS_BLOCKED, _("Blocked")),
    (PROGRESS_STATUS_PENDING, _("Pending")),
    (PROGRESS_STATUS_IGNORED, _("ignored")),
)

PROGRESS_STATUS_FORCE_UPDATE = [
    PROGRESS_STATUS_REPROC,
    PROGRESS_STATUS_TODO,
    PROGRESS_STATUS_DONE,
    PROGRESS_STATUS_PENDING,
    PROGRESS_STATUS_BLOCKED,
]

PROGRESS_STATUS_REGULAR_TODO = [
    PROGRESS_STATUS_REPROC,
    PROGRESS_STATUS_TODO,
]


def allowed_to_run(status, force_update):
    return force_update and status in PROGRESS_STATUS_FORCE_UPDATE or status in PROGRESS_STATUS_TODO
