"""
Telas (admin) da complementação de coleções, restritas a administradores
(superusuários):

1. formulário: periódico, coleções origem e destino e intervalo de anos
2. seleção dos fascículos da coleção origem (todos selecionados) e
   confirmação, que dispara as tarefas
3. relatório: adicionados, ignorados (com o motivo) e erros
"""

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from collection_completion import choices, handlers
from collection_completion.forms import CollectionCompletionForm, IssueSelectionForm
from collection_completion.models import CollectionCompletion
from collection_completion.tasks import dispatch_issue_tasks


def is_admin(user):
    if user.is_authenticated and user.is_superuser:
        return True
    raise PermissionDenied


admin_required = user_passes_test(is_admin)


def get_source_issues(form):
    return handlers.get_source_issues(
        form.cleaned_data["journal"],
        form.cleaned_data["source_collection"],
        form.cleaned_data["target_collection"],
        form.years,
    )


@admin_required
def completion_list(request):
    return render(
        request,
        "collection_completion/list.html",
        {"completions": CollectionCompletion.objects.select_related(
            "journal", "source_collection", "target_collection", "creator"
        )[:100]},
    )


@admin_required
def completion_create(request):
    """
    Formulário (GET) e seleção dos fascículos (POST válido)
    """
    form = CollectionCompletionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        source_issues = get_source_issues(form)
        if not source_issues:
            messages.warning(
                request,
                _("No issues of the journal in the source collection for the years {}-{}").format(
                    form.cleaned_data["start_year"], form.cleaned_data["end_year"]
                ),
            )
        else:
            return render(
                request,
                "collection_completion/select_issues.html",
                {
                    "form": form,
                    "issues_form": IssueSelectionForm(source_issues=source_issues),
                },
            )
    return render(request, "collection_completion/form.html", {"form": form})


@admin_required
@require_POST
def completion_confirm(request):
    """
    Cria a complementação com os fascículos selecionados e dispara uma
    tarefa para cada fascículo (que dispara as dos seus artigos)
    """
    form = CollectionCompletionForm(request.POST)
    if not form.is_valid():
        return render(request, "collection_completion/form.html", {"form": form})

    issues_form = IssueSelectionForm(
        request.POST, source_issues=get_source_issues(form)
    )
    if not issues_form.is_valid():
        return render(
            request,
            "collection_completion/select_issues.html",
            {"form": form, "issues_form": issues_form},
        )

    user = request.user
    completion = CollectionCompletion.create(
        user,
        form.cleaned_data["journal"],
        form.cleaned_data["source_collection"],
        form.cleaned_data["target_collection"],
        form.cleaned_data["start_year"],
        form.cleaned_data["end_year"],
    )
    items = [
        completion.add_item(
            user,
            choices.ITEM_TYPE_ISSUE,
            issue["id"],
            label=issue["label"],
            source_pid=issue.get("source_pid"),
        )
        for issue in issues_form.selected_issues
    ]
    dispatch_issue_tasks(items, user.id)
    messages.success(
        request,
        _("Collection completion started: {} issue(s)").format(len(items)),
    )
    return redirect("collection_completion:report", pk=completion.pk)


@admin_required
def completion_report(request, pk):
    completion = get_object_or_404(
        CollectionCompletion.objects.select_related(
            "journal", "source_collection", "target_collection", "creator"
        ),
        pk=pk,
    )
    report = completion.get_report()
    totals = report["totals"]
    rows = [
        {
            "item_type": label,
            "values": [
                totals.get(item_type, {}).get(status, 0)
                for status, _status_label in choices.STATUS
            ],
        }
        for item_type, label in choices.ITEM_TYPES
    ]
    sections = [
        {"status": status, "label": label, "items": report["items"][status]}
        for status, label in choices.STATUS
        if report["items"][status]
    ]
    return render(
        request,
        "collection_completion/report.html",
        {
            "completion": completion,
            "is_finished": report["is_finished"],
            "status_labels": [label for _status, label in choices.STATUS],
            "rows": rows,
            "sections": sections,
        },
    )
