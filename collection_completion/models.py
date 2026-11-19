"""
Complementação de coleções: adiciona à coleção destino os fascículos e
artigos que um periódico presente em mais de uma coleção tem na coleção
origem.

O registro (CollectionCompletion) e os itens (CollectionCompletionItem) são
o relatório da complementação: adicionados, ignorados (com o motivo) e
erros. Cada item é processado por uma tarefa Celery (ver tasks.py) e as
regras de cada sistema (Core e Upload) estão em handlers.py.

A complementação não publica o conteúdo; a publicação é outra ação.
"""

from django.db import models
from django.db.models import Count
from django.utils.translation import gettext_lazy as _

from collection.models import Collection
from collection_completion import choices
from core.models import CommonControlField
from journal.models import Journal


class CollectionCompletion(CommonControlField):
    journal = models.ForeignKey(
        Journal,
        verbose_name=_("Journal"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    source_collection = models.ForeignKey(
        Collection,
        verbose_name=_("Source collection"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    target_collection = models.ForeignKey(
        Collection,
        verbose_name=_("Target collection"),
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    start_year = models.CharField(_("Start year"), max_length=4)
    end_year = models.CharField(_("End year"), max_length=4)

    class Meta:
        verbose_name = _("Collection completion")
        verbose_name_plural = _("Collection completions")
        ordering = ["-created"]

    def __str__(self):
        return (
            f"{self.journal} {self.source_collection} -> {self.target_collection} "
            f"{self.start_year}-{self.end_year}"
        )

    @classmethod
    def create(
        cls, user, journal, source_collection, target_collection, start_year, end_year
    ):
        obj = cls(
            journal=journal,
            source_collection=source_collection,
            target_collection=target_collection,
            start_year=str(start_year),
            end_year=str(end_year),
            creator=user,
        )
        obj.save()
        return obj

    def add_item(
        self, user, item_type, source_id, label=None, source_pid=None, parent=None
    ):
        return CollectionCompletionItem.objects.create(
            completion=self,
            parent=parent,
            item_type=item_type,
            source_id=str(source_id),
            label=(label or "")[:255],
            source_pid=source_pid,
            creator=user,
        )

    @property
    def is_finished(self):
        return not self.items.filter(status=choices.STATUS_TODO).exists()

    @property
    def totals(self):
        """
        Totais por tipo de item e situação
        Ex.: {"issue": {"added": 2, "ignored": 1}, "article": {"added": 30}}
        """
        totals = {}
        for row in (
            self.items.values("item_type", "status")
            .annotate(total=Count("id"))
            .order_by()
        ):
            totals.setdefault(row["item_type"], {})[row["status"]] = row["total"]
        return totals

    def get_report(self):
        """
        Relatório da complementação: totais e itens por situação
        """
        items = {status: [] for status, _label in choices.STATUS}
        for item in self.items.select_related("parent").order_by("item_type", "id"):
            items[item.status].append(item)
        return {
            "is_finished": self.is_finished,
            "totals": self.totals,
            "items": items,
        }


class CollectionCompletionItem(CommonControlField):
    completion = models.ForeignKey(
        CollectionCompletion,
        on_delete=models.CASCADE,
        related_name="items",
    )
    # artigo: item do fascículo ao qual pertence
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    item_type = models.CharField(
        _("Item type"), max_length=8, choices=choices.ITEM_TYPES
    )
    # id do registro da coleção origem (Core: Issue / Article; Upload:
    # IssueProc / ArticleProc)
    source_id = models.CharField(_("Source id"), max_length=64)
    label = models.CharField(_("Label"), max_length=255, null=True, blank=True)
    source_pid = models.CharField(
        _("Source PID"), max_length=23, null=True, blank=True
    )
    target_pid = models.CharField(
        _("Target PID"), max_length=23, null=True, blank=True
    )
    status = models.CharField(
        _("Status"),
        max_length=8,
        choices=choices.STATUS,
        default=choices.STATUS_TODO,
    )
    reason = models.TextField(_("Reason"), null=True, blank=True)
    detail = models.JSONField(_("Detail"), null=True, blank=True)

    class Meta:
        verbose_name = _("Collection completion item")
        verbose_name_plural = _("Collection completion items")
        indexes = [
            models.Index(fields=["completion", "status"]),
            models.Index(fields=["completion", "item_type"]),
        ]

    def __str__(self):
        return f"{self.get_item_type_display()} {self.label or self.source_pid} [{self.status}]"

    def finish(
        self, user, status, reason=None, source_pid=None, target_pid=None, detail=None
    ):
        self.status = status
        self.reason = reason and str(reason)
        self.source_pid = source_pid or self.source_pid
        self.target_pid = target_pid or self.target_pid
        self.detail = detail
        self.updated_by = user
        self.save()
