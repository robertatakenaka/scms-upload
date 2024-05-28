import logging

from django import forms
from django.utils.translation import gettext_lazy as _
from wagtail.admin.forms import WagtailAdminModelForm

from upload import choices


class UploadPackageForm(WagtailAdminModelForm):
    def save(self, commit=True):
        upload_package = super().save(commit=False)
        if upload_package.qa_decision:
            upload_package.status = self.instance.qa_decision
        upload_package.save()
        return upload_package

    def save_all(self, user):
        upload_package = super().save(commit=False)

        if self.instance.pk is None:
            upload_package.creator = user
            upload_package.save()

        self.save()

        return upload_package


class ValidationResultForm(WagtailAdminModelForm):
    def save_all(self, user):
        vr_obj = super().save(commit=False)

        if self.instance.pk is None:
            vr_obj.creator = user

        self.save()

        return vr_obj


ErrorNegativeReactionForm = ValidationResultForm
ErrorNegativeReactionDecisionForm = ValidationResultForm


class XMLErrorReportForm(WagtailAdminModelForm):
    def clean(self):
        cleaned_data = super().clean()
        xml_error = cleaned_data.get("xml_error")

        for item in self.xml_error.filter(reaction=choices.ER_REACTION_JUSTIFY):
            if item.non_error_justification.count() == 0:
                self.add_error(
                    "xml_error",
                    _(f"Error {item.error_id} requires justification for not correcting")
                )
            else:
                for just in item.non_error_justification.all():
                    if not just.justification.strip():
                        self.add_error(
                            "xml_error",
                            _(f"Error {item.error_id} requires justification for not correcting")
                        )


class ValidationResultErrorResolutionForm(forms.Form):
    validation_result_id = forms.IntegerField()
    rationale = forms.CharField(widget=forms.Textarea, required=False)
    action = forms.CharField(widget=forms.Select, required=False)


class ValidationResultErrorResolutionOpinionForm(forms.Form):
    validation_result_id = forms.IntegerField()
    guidance = forms.CharField(widget=forms.Textarea, required=False)
    opinion = forms.CharField(widget=forms.Select, required=False)
