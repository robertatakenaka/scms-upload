from django import forms
from django.utils.translation import gettext_lazy as _

from collection.models import Collection
from collection_completion import handlers
from journal.models import Journal


class CollectionCompletionForm(forms.Form):
    """
    Periódico, coleções origem e destino e intervalo de anos dos
    fascículos a completar
    """

    journal = forms.ModelChoiceField(
        label=_("Journal"),
        queryset=Journal.objects.none(),
        help_text=_("Journals present in more than one collection"),
    )
    source_collection = forms.ModelChoiceField(
        label=_("Source collection"), queryset=Collection.objects.all()
    )
    target_collection = forms.ModelChoiceField(
        label=_("Target collection"), queryset=Collection.objects.all()
    )
    start_year = forms.IntegerField(label=_("Start year"), min_value=1800, max_value=2100)
    end_year = forms.IntegerField(label=_("End year"), min_value=1800, max_value=2100)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["journal"].queryset = handlers.get_journals_queryset()

    def clean(self):
        cleaned_data = super().clean()
        journal = cleaned_data.get("journal")
        source = cleaned_data.get("source_collection")
        target = cleaned_data.get("target_collection")
        start_year = cleaned_data.get("start_year")
        end_year = cleaned_data.get("end_year")

        if source and target and source == target:
            raise forms.ValidationError(
                _("The source and target collections must be different")
            )
        if start_year and end_year and start_year > end_year:
            raise forms.ValidationError(
                _("The start year must be less than or equal to the end year")
            )
        if journal and source and target:
            journal_collections = set(handlers.get_journal_collections(journal))
            missing = [
                str(collection)
                for collection in (source, target)
                if collection not in journal_collections
            ]
            if missing:
                raise forms.ValidationError(
                    _("The journal is not in the collection(s): {}. Journal collections: {}").format(
                        ", ".join(missing),
                        ", ".join(str(c) for c in journal_collections),
                    )
                )
        return cleaned_data

    @property
    def years(self):
        return [
            str(year)
            for year in range(
                self.cleaned_data["start_year"], self.cleaned_data["end_year"] + 1
            )
        ]


class IssueSelectionForm(forms.Form):
    """
    Fascículos da coleção origem a completar; todos selecionados por padrão
    """

    issues = forms.MultipleChoiceField(
        label=_("Issues"),
        widget=forms.CheckboxSelectMultiple,
        required=True,
    )

    def __init__(self, *args, source_issues=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.source_issues = {item["id"]: item for item in source_issues or []}
        self.fields["issues"].choices = [
            (item["id"], self.get_choice_label(item)) for item in source_issues or []
        ]
        if not self.is_bound:
            self.initial["issues"] = list(self.source_issues.keys())

    @staticmethod
    def get_choice_label(item):
        label = f"{item['label']} | {item.get('source_pid') or '-'}"
        if item.get("target_pid"):
            label = f"{label} | " + str(
                _("already in the target collection: {}")
            ).format(item["target_pid"])
        return label

    @property
    def selected_issues(self):
        return [self.source_issues[id_] for id_ in self.cleaned_data["issues"]]
