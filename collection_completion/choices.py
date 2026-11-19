from django.utils.translation import gettext_lazy as _

ITEM_TYPE_ISSUE = "issue"
ITEM_TYPE_ARTICLE = "article"
ITEM_TYPES = (
    (ITEM_TYPE_ISSUE, _("Issue")),
    (ITEM_TYPE_ARTICLE, _("Article")),
)

# aguardando a tarefa
STATUS_TODO = "todo"
# adicionado à coleção destino
STATUS_ADDED = "added"
# não adicionado, com o motivo (ex.: já está na coleção destino)
STATUS_IGNORED = "ignored"
# falha inesperada
STATUS_ERROR = "error"
STATUS = (
    (STATUS_TODO, _("To do")),
    (STATUS_ADDED, _("Added")),
    (STATUS_IGNORED, _("Ignored")),
    (STATUS_ERROR, _("Error")),
)
FINAL_STATUS = (STATUS_ADDED, STATUS_IGNORED, STATUS_ERROR)
