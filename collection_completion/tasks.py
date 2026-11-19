"""
Tarefas da complementação de coleções: uma tarefa por item (fascículo e
artigo). A tarefa do fascículo cria os itens dos artigos do fascículo de
origem e dispara uma tarefa para cada um.

As regras de cada sistema (Core e Upload) estão em handlers.py.
"""

import traceback

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.translation import gettext as _

from collection_completion import choices, handlers
from collection_completion.models import CollectionCompletionItem
from config import celery_app

User = get_user_model()


def dispatch_issue_tasks(items, user_id):
    """
    Dispara a tarefa de cada item de fascículo, após a gravação dos itens
    """
    for item in items:
        transaction.on_commit(
            lambda item_id=item.id: task_complete_issue.apply_async(
                kwargs={"item_id": item_id, "user_id": user_id}
            )
        )


def _finish_with_error(item, user, exception):
    item.finish(
        user,
        choices.STATUS_ERROR,
        reason=f"{type(exception).__name__}: {exception}",
        detail={"traceback": traceback.format_exc()},
    )


@celery_app.task(bind=True)
def task_complete_issue(self, item_id, user_id):
    user = User.objects.get(pk=user_id)
    item = CollectionCompletionItem.objects.select_related(
        "completion__journal",
        "completion__source_collection",
        "completion__target_collection",
    ).get(pk=item_id)
    completion = item.completion
    try:
        result = handlers.complete_issue(
            user,
            completion.journal,
            completion.source_collection,
            completion.target_collection,
            item.source_id,
        )
    except Exception as e:
        _finish_with_error(item, user, e)
        return

    target_issue_id = result.get("target_issue_id")
    articles = []
    for article in result.get("articles") or []:
        child = completion.add_item(
            user,
            choices.ITEM_TYPE_ARTICLE,
            article["id"],
            label=article.get("label"),
            source_pid=article.get("pid"),
            parent=item,
        )
        if target_issue_id:
            articles.append(child)
        else:
            # fascículo indisponível na coleção destino
            child.finish(
                user,
                choices.STATUS_IGNORED,
                reason=_("The issue is not in the target collection: {}").format(
                    result.get("reason")
                ),
            )

    item.finish(
        user,
        result["status"],
        reason=result.get("reason"),
        source_pid=result.get("source_pid"),
        target_pid=result.get("target_pid"),
        detail=result.get("detail"),
    )

    for child in articles:
        transaction.on_commit(
            lambda child_id=child.id: task_complete_article.apply_async(
                kwargs={
                    "item_id": child_id,
                    "user_id": user_id,
                    "target_issue_id": target_issue_id,
                }
            )
        )


@celery_app.task(bind=True)
def task_complete_article(self, item_id, user_id, target_issue_id):
    user = User.objects.get(pk=user_id)
    item = CollectionCompletionItem.objects.select_related(
        "completion__source_collection",
        "completion__target_collection",
    ).get(pk=item_id)
    completion = item.completion
    try:
        result = handlers.complete_article(
            user,
            completion.source_collection,
            completion.target_collection,
            item.source_id,
            target_issue_id,
        )
    except Exception as e:
        _finish_with_error(item, user, e)
        return

    item.finish(
        user,
        result["status"],
        reason=result.get("reason"),
        source_pid=result.get("source_pid"),
        target_pid=result.get("target_pid"),
        detail=result.get("detail"),
    )
