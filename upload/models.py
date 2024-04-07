from datetime import date, timedelta, datetime

from django.contrib.auth import get_user_model
from django.db import models, IntegrityError
from django.utils.translation import gettext_lazy as _
from wagtail.admin.panels import FieldPanel, MultiFieldPanel, InlinePanel
from wagtailautocomplete.edit_handlers import AutocompletePanel
from modelcluster.models import ClusterableModel

from article.models import Article
from core.models import CommonControlField
from issue.models import Issue
from journal.models import Journal

from . import choices
from .forms import UploadPackageForm, ValidationResultForm
from .permission_helper import (
    ACCESS_ALL_PACKAGES,
    ANALYSE_VALIDATION_ERROR_RESOLUTION,
    ASSIGN_PACKAGE,
    FINISH_DEPOSIT,
    SEND_VALIDATION_ERROR_RESOLUTION,
)
from .utils import file_utils

User = get_user_model()


class Package(CommonControlField):
    file = models.FileField(_("Package File"), null=False, blank=False)
    signature = models.CharField(_("Signature"), max_length=32, null=True, blank=True)
    category = models.CharField(
        _("Category"),
        max_length=32,
        choices=choices.PACKAGE_CATEGORY,
        null=False,
        blank=False,
    )
    status = models.CharField(
        _("Status"),
        max_length=32,
        choices=choices.PACKAGE_STATUS,
        default=choices.PS_ENQUEUED_FOR_VALIDATION,
    )
    article = models.ForeignKey(
        Article,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
    )
    journal = models.ForeignKey(
        Journal, blank=True, null=True, on_delete=models.SET_NULL
    )
    issue = models.ForeignKey(Issue, blank=True, null=True, on_delete=models.SET_NULL)
    assignee = models.ForeignKey(User, blank=True, null=True, on_delete=models.SET_NULL)
    expiration_date = models.DateField(_("Expiration date"), null=True, blank=True)

    autocomplete_search_field = "file"

    def autocomplete_label(self):
        return f"{self.file.name} - {self.category} - {self.article or self.issue} ({self.status})"

    panels = [
        FieldPanel("file"),
    ]

    def __str__(self):
        return self.file.name

    def save(self, *args, **kwargs):
        self.expiration_date = date.today() + timedelta(days=30)
        super(Package, self).save(*args, **kwargs)

    def files_list(self):
        files = {"files": []}

        try:
            files.update({"files": file_utils.get_file_list_from_zip(self.file.path)})
        except file_utils.BadPackageFileError:
            # É preciso capturar esta exceção para garantir que aqueles que
            #  usam files_list obtenham, na pior das hipóteses, um dicionário do tipo {'files': []}.
            # Isto pode ocorrer quando o zip for inválido, por exemplo.
            ...

        return files

    base_form_class = UploadPackageForm

    class Meta:
        permissions = (
            (FINISH_DEPOSIT, _("Can finish deposit")),
            (ACCESS_ALL_PACKAGES, _("Can access all packages from all users")),
            (ASSIGN_PACKAGE, _("Can assign package")),
        )

    @classmethod
    def add_validation_result(
        cls, package_id, error_category=None, status=None, message=None, data=None
    ):
        package = cls.objects.get(pk=package_id)
        val_res = package._add_validation_result(error_category, status, message, data)
        return val_res

    def _add_validation_result(
        self, error_category=None, status=None, message=None, data=None
    ):
        val_res = ValidationResult.create(error_category, self, status, message, data)
        self.update_status(val_res)
        return val_res

    def update_status(self, validation_result):
        if validation_result.status == choices.VALIDATION_RESULT_SUCCESS:
            self.status = choices.PS_ENQUEUED_FOR_VALIDATION
            self.save()
            return
        if validation_result.status == choices.VALIDATION_RESULT_FAILURE:
            self.status = choices.PS_REJECTED
            self.save()
            return
        if validation_result.status == choices.VS_DISAPPROVED:
            self.status = choices.PS_REJECTED
            self.save()

    @classmethod
    def get(cls, pkg_id=None, article=None):
        if pkg_id:
            return cls.objects.get(pk=pkg_id)
        if article:
            return cls.objects.get(article=article)

    @classmethod
    def create(cls, user_id, file, article_id=None, category=None, status=None):
        obj = cls()
        obj.article_id = article_id
        obj.creator_id = user_id
        obj.created = datetime.utcnow()
        obj.file = file
        obj.category = category or choices.PC_SYSTEM_GENERATED
        obj.status = status or choices.PS_PUBLISHED
        obj.save()
        return obj

    @classmethod
    def create_or_update(cls, user_id, file, article=None, category=None, status=None):
        try:
            obj = cls.get(article=article)
            obj.article = article
            obj.file = file
            obj.category = category
            obj.status = status
            obj.save()
            return obj
        except cls.DoesNotExist:
            return cls.create(
                user_id, file, article_id=article.id, category=category, status=status
            )

    def check_resolutions(self):
        try:
            item = self.validationresult_set.filter(
                status=choices.VS_DISAPPROVED,
                resolution__action__in=[choices.ER_ACTION_TO_FIX, ""],
            )[0]
            self.status = choices.PS_PENDING_CORRECTION
        except IndexError:
            self.status = choices.PS_READY_TO_BE_FINISHED
        self.save()
        return self.status

    def check_opinions(self):
        try:
            item = self.validationresult_set.filter(
                status=choices.VS_DISAPPROVED,
                analysis__opinion__in=[choices.ER_OPINION_FIX_DEMANDED, ""],
            )[0]
            self.status = choices.PS_PENDING_CORRECTION
        except IndexError:
            self.status = choices.PS_ACCEPTED
        self.save()
        return self.status

    def check_finish(self):
        if self.status == choices.PS_READY_TO_BE_FINISHED:
            self.status = choices.PS_QA
            self.save()
            return True

        return False

    @property
    def data(self):
        return dict(
            file=self.file.name,
            status=self.status,
            category=self.category,
            journal=self.journal and self.journal.data,
            issue=self.issue and self.issue.data,
            article=self.article and self.article.data,
            assignee=str(self.assignee),
            expiration_date=str(expiration_date),
        )


class QAPackage(Package):
    class Meta:
        proxy = True


class ValidationResult(models.Model):
    id = models.AutoField(primary_key=True)
    category = models.CharField(
        _("Error category"),
        max_length=32,
        choices=choices.VALIDATION_ERROR_CATEGORY,
        null=False,
        blank=False,
    )
    data = models.JSONField(_("Error data"), default=dict, null=True, blank=True)
    message = models.TextField(_("Error message"), null=True, blank=True)
    status = models.CharField(
        _("Status"),
        max_length=16,
        choices=choices.VALIDATION_STATUS,
        null=True,
        blank=True,
    )

    package = models.ForeignKey(
        "Package", on_delete=models.CASCADE, null=False, blank=False
    )

    def __str__(self):
        return "-".join(
            [
                str(self.id),
                self.package.file.name,
                self.category,
                self.status,
            ]
        )

    def report_name(self):
        return choices.VALIDATION_DICT_ERROR_CATEGORY_TO_REPORT[self.category]

    panels = [
        MultiFieldPanel(
            [
                AutocompletePanel("package"),
                FieldPanel("category"),
            ],
            heading=_("Identification"),
            classname="collapsible",
        ),
        MultiFieldPanel(
            [
                FieldPanel("status"),
                FieldPanel("data"),
                FieldPanel("message"),
            ],
            heading=_("Content"),
            classname="collapsible",
        ),
    ]

    class Meta:
        permissions = (
            (SEND_VALIDATION_ERROR_RESOLUTION, _("Can send error resolution")),
            (ANALYSE_VALIDATION_ERROR_RESOLUTION, _("Can analyse error resolution")),
        )

    base_form_class = ValidationResultForm

    @classmethod
    def create(cls, error_category, package, status=None, message=None, data=None):
        val_res = ValidationResult()
        val_res.category = error_category
        val_res.package = package
        val_res.status = status
        val_res.message = message
        val_res.data = data
        val_res.save()
        return val_res

    def update(self, error_category, status=None, message=None, data=None):
        self.category = error_category
        self.status = status
        self.message = message
        self.data = data
        self.save()

        self.package.update_status(self)

    @classmethod
    def add_resolution(cls, user, data):
        validation_result = cls.objects.get(pk=data["validation_result_id"].value())

        try:
            opinion = data["opinion"].value()
            return ErrorResolutionOpinion.create_or_update(
                user=user,
                validation_result=validation_result,
                opinion=opinion,
                guidance=data["guidance"].value(),
            )
        except KeyError:
            return ErrorResolution.create_or_update(
                user=user,
                validation_result=validation_result,
                action=data["action"].value(),
                rationale=data["rationale"].value(),
            )


class ErrorResolution(CommonControlField):
    validation_result = models.OneToOneField(
        "ValidationResult",
        to_field="id",
        primary_key=True,
        related_name="resolution",
        on_delete=models.CASCADE,
    )
    action = models.CharField(
        _("Action"),
        max_length=32,
        choices=choices.ERROR_RESOLUTION_ACTION,
        default=choices.ER_ACTION_TO_FIX,
        null=True,
        blank=True,
    )
    rationale = models.TextField(_("Rationale"), null=True, blank=True)

    panels = [
        FieldPanel("action"),
        FieldPanel("rationale"),
    ]

    @classmethod
    def get(cls, validation_result):
        return cls.objects.get(validation_result=validation_result)

    @classmethod
    def create(cls, user, validation_result, action, rationale):
        obj = cls()
        obj.creator = user
        obj.created = datetime.now()
        obj.validation_result = validation_result
        obj.action = action
        obj.rationale = rationale
        obj.save()
        return obj

    @classmethod
    def create_or_update(cls, user, validation_result, action, rationale):
        try:
            obj = cls.get(validation_result)
            obj.updated = datetime.now()
            obj.updated_by = user
            obj.action = action
            obj.rationale = rationale
            obj.save()
        except cls.DoesNotExist:
            obj = cls.create(user, validation_result, action, rationale)
        return obj


class ErrorResolutionOpinion(CommonControlField):
    validation_result = models.OneToOneField(
        "ValidationResult",
        to_field="id",
        primary_key=True,
        related_name="analysis",
        on_delete=models.CASCADE,
    )
    opinion = models.CharField(
        _("Opinion"),
        max_length=32,
        choices=choices.ERROR_RESOLUTION_OPINION,
        null=True,
        blank=True,
    )
    guidance = models.TextField(_("Guidance"), max_length=512, null=True, blank=True)

    panels = [
        FieldPanel("opinion"),
        FieldPanel("guidance"),
    ]

    @classmethod
    def get(cls, validation_result):
        return cls.objects.get(validation_result=validation_result)

    @classmethod
    def create(cls, user, validation_result, opinion, guidance):
        obj = cls()
        obj.creator = user
        obj.created = datetime.now()
        obj.validation_result = validation_result
        obj.opinion = opinion
        obj.guidance = guidance
        obj.save()
        return obj

    @classmethod
    def create_or_update(cls, user, validation_result, opinion, guidance):
        try:
            obj = cls.get(validation_result)
            obj.updated = datetime.now()
            obj.updated_by = user
            obj.save()
        except cls.DoesNotExist:
            obj = cls.create(user, validation_result, opinion, guidance)
        return obj


class BaseValidationReport(CommonControlField):
    title = models.CharField(_("Title"), null=True, blank=True, max_length=128)
    package = models.ForeignKey(
        Package,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="package",
    )
    category = models.CharField(
        _("Error category"),
        max_length=32,
        choices=choices.VALIDATION_ERROR_CATEGORY,
        null=False,
        blank=False,
    )
    panels = [
        AutocompletePanel("package", read_only=True),
        FieldPanel("title", read_only=True),
    ]

    def __str__(self):
        return f"{self.package} {self.title}"

    class Meta:
        abstract = True
        verbose_name = _("Validation Report")
        verbose_name_plural = _("Validation Reports")
        unique_together = [
            (
                "package",
                "title",
            )
        ]
        indexes = [
            models.Index(
                fields=[
                    "title",
                ]
            ),
        ]

    @classmethod
    def get(cls, package=None, title=None, category=None):
        return cls.objects.get(package=package, title=title, category=category)

    @classmethod
    def create(cls, user, package=None, title=None, category=None):
        try:
            val_res = cls()
            val_res.user = user
            val_res.package = package
            val_res.title = title
            val_res.category = category
            val_res.save()
            return val_res
        except IntegrityError:
            return cls.get(package, title, category)

    @classmethod
    def get_or_create(cls, user, package, title, category):
        try:
            return cls.get(package, title, category)
        except cls.DoesNotExist:
            return cls.create(user, package, title, category)


class ValidationReport(BaseValidationReport, ClusterableModel):
    panels = super().panels + [InlinePanel("validation_result", label=_("Result"))]

    def add_validation_result(
        self,
        status=None,
        message=None,
        data=None,
        subject=None,
    ):
        validation_result = PkgValidationResult.create(
            subject=subject or data.get("subject"),
            status=status,
            message=message,
            data=data,
            creator=self.creator,
        )
        validation_result.report = self
        validation_result.save()
        return validation_result


class XMLInfoReport(BaseValidationReport, ClusterableModel):
    panels = super().panels + [InlinePanel("xml_info", label=_("Result"))]


class XMLErrorReport(BaseValidationReport, ClusterableModel):
    panels = super().panels + [InlinePanel("xml_error", label=_("Error"))]


class BaseValidationResult(CommonControlField):
    subject = models.CharField(
        _("Subject"),
        null=True,
        blank=True,
        max_length=128,
        help_text=_("Item is being analyzed"),
    )
    data = models.JSONField(_("Data"), default=dict, null=True, blank=True)
    message = models.TextField(_("Message"), null=True, blank=True)
    status = models.CharField(
        _("Result"),
        max_length=16,
        choices=choices.VALIDATION_RESULT,
        default=choices.VALIDATION_RESULT_UNKNOWN,
        null=True,
        blank=True,
    )

    base_form_class = ValidationResultForm
    panels = [
        FieldPanel("subject", read_only=True),
        FieldPanel("status", read_only=True),
        FieldPanel("message", read_only=True),
        FieldPanel("data", read_only=True),
    ]

    autocomplete_search_field = "subject"

    def autocomplete_label(self):
        return self.info

    def __str__(self):
        return "-".join(
            [
                self.subject,
                self.status,
            ]
        )

    class Meta:
        abstract = True
        verbose_name = _("Validation result")
        verbose_name_plural = _("Validation results")
        indexes = [
            models.Index(
                fields=[
                    "subject",
                ]
            ),
            models.Index(
                fields=[
                    "status",
                ]
            ),
        ]

    @classmethod
    def create(cls, subject=None, status=None, message=None, data=None, creator=None):
        val_res = cls()
        val_res.subject = subject
        val_res.status = status
        val_res.message = message
        val_res.data = data
        val_res.creator = creator

        val_res.save()
        return val_res

    def update(self, status=None, message=None, data=None, updated_by=None):
        self.status = status
        self.message = message
        self.data = data
        self.updated_by = updated_by
        self.save()

    @property
    def info(self):
        return dict(
            subject=self.subject,
            status=self.status,
            message=self.message,
        )


class PkgValidationResult(BaseValidationResult):
    report = models.ForeignKey(
        ValidationReport,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="validation_result",
    )


class BaseXMLValidationResult(BaseValidationResult):
    # BaseValidationResult.status = response (ok -> success, 'error' -> failure)
    # BaseValidationResult.subject = item do resultado de validação do packtools
    # BaseValidationResult.message = message
    # BaseValidationResult.data = data

    # attribute = sub_item do resultado de validação do packtools
    attribute = models.CharField(
        _("Subject AttributeError"), null=True, blank=True, max_length=32
    )
    # geralemente article / sub-article e id
    parent = models.CharField(_("Parent"), null=True, blank=True, max_length=32)
    parent_id = models.CharField(_("Parent id"), null=True, blank=True, max_length=8)

    # focus = title do resultado de validação do packtools
    focus = models.CharField(_("Analysis focus"), null=True, blank=True, max_length=64)
    # validation_type = packtools validation_type
    validation_type = models.CharField(
        _("Validation type"),
        max_length=16,
        null=False,
        blank=False,
    )

    panels = [
        FieldPanel("status", read_only=True),
        FieldPanel("subject", read_only=True),
        FieldPanel("attribute", read_only=True),
        FieldPanel("focus", read_only=True),
        FieldPanel("parent", read_only=True),
        FieldPanel("parent_id", read_only=True),
        FieldPanel("data", read_only=True),
        FieldPanel("message", read_only=True),
    ]

    @property
    def info(self):
        return dict(
            status=self.status,
            subject=self.subject,
            attribute=self.attribute,
            focus=self.focus,
            parent=self.parent,
            parent_id=self.parent_id,
            data=self.data,
            message=self.message,
        )

    def __str__(self):
        return str(self.info)

    class Meta:
        verbose_name = _("XML validation result")
        verbose_name_plural = _("XML validation results")

        indexes = [
            models.Index(
                fields=[
                    "attribute",
                ]
            ),
            models.Index(
                fields=[
                    "validation_type",
                ]
            ),
            models.Index(
                fields=[
                    "attribute",
                ]
            ),
        ]


class XMLInfo(BaseXMLValidationResult):
    report = models.ForeignKey(
        ValidationReport,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="xml_info",
    )


class XMLError(BaseXMLValidationResult, ClusterableModel):
    report = models.ForeignKey(
        ValidationReport,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="xml_error",
    )
    expected_value = models.JSONField(
        _("Expected value"),
        null=True,
        blank=True,
    )
    got_value = models.JSONField(_("Got value"), null=True, blank=True)
    advice = models.CharField(_("Advice"), null=True, blank=True, max_length=128)
    reaction = models.CharField(
        _("Reaction"),
        max_length=32,
        choices=choices.ERROR_REACTION,
        default=choices.ER_ACTION_TO_FIX,
        null=True,
        blank=True,
    )
    base_form_class = ValidationResultForm

    panels = [
        FieldPanel("status", read_only=True),
        FieldPanel("subject", read_only=True),
        FieldPanel("attribute", read_only=True),
        FieldPanel("focus", read_only=True),
        FieldPanel("parent", read_only=True),
        FieldPanel("parent_id", read_only=True),
        FieldPanel("data", read_only=True),
        FieldPanel("expected_value", read_only=True),
        FieldPanel("got_value", read_only=True),
        FieldPanel("message", read_only=True),
        FieldPanel("advice", read_only=True),
        FieldPanel("reaction", read_only=True),
        InlinePanel(
            "non_error_justification", max_num=1, label=_("Non-error justification")
        ),
    ]

    class Meta:
        verbose_name = _("XML error")
        verbose_name_plural = _("XML errors")
        indexes = [
            models.Index(
                fields=[
                    "reaction",
                ]
            ),
        ]


class ErrorNegativeReaction(CommonControlField):
    error = models.ForeignKey(
        XMLError,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="non_error_justification",
    )

    justification = models.CharField(
        _("Non-error justification"), max_length=128, null=True, blank=True
    )

    base_form_class = ErrorNegativeReactionForm

    panels = [
        FieldPanel("justification"),
        InlinePanel("qa_decision", label=_("Quality Analyst Decision")),
    ]

    class Meta:
        verbose_name = _("Non-error justification")
        verbose_name_plural = _("Non-error justifications")
        permissions = (
            (SEND_VALIDATION_ERROR_RESOLUTION, _("Can send justification not to fix")),
        )


class ErrorNegativeReactionDecision(CommonControlField):
    error_negative_reaction = models.ForeignKey(
        ErrorNegativeReaction,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="qa_decision",
    )

    decision = models.CharField(
        _("Decision"),
        max_length=32,
        choices=choices.ERROR_DECISION,
        default=choices.ER_DECISION_FIX_REQUIRED,
        null=True,
        blank=True,
    )
    decision_argument = models.CharField(
        _("Decision argument"), max_length=128, null=True, blank=True
    )

    base_form_class = ErrorNegativeReactionDecisionForm

    panels = [
        FieldPanel("decision"),
        FieldPanel("decision_argument"),
    ]

    class Meta:
        permissions = (
            (
                ANALYSE_VALIDATION_ERROR_RESOLUTION,
                _("Can decide about the correction demand"),
            ),
        )
