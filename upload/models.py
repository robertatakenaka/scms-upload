from datetime import date, timedelta
from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import gettext_lazy as _

from wagtailautocomplete.edit_handlers import AutocompletePanel
from wagtail.admin.edit_handlers import FieldPanel, MultiFieldPanel

from article.models import Article
from core.models import CommonControlField
from issue.models import Issue
from files_storage.models import MinioFile
from . import choices
from .forms import UploadPackageForm, ValidationResultForm
from .permission_helper import ACCESS_ALL_PACKAGES, ASSIGN_PACKAGE, ANALYSE_VALIDATION_ERROR_RESOLUTION, FINISH_DEPOSIT, SEND_VALIDATION_ERROR_RESOLUTION
from .utils import file_utils


User = get_user_model()


class Event(models.Model):
    date = models.DateField(_('Date'), null=True, blank=True, auto_now=True)
    user = models.ForeignKey(User, blank=True, null=True, on_delete=models.SET_NULL)
    event = models.CharField(_("Event"), max_length=255, null=True, blank=True)
    status = models.CharField(_('Status'), max_length=32, choices=choices.PACKAGE_STATUS, default=choices.PS_ENQUEUED_FOR_VALIDATION)

    class Meta:

        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['user']),
            models.Index(fields=['event']),
            models.Index(fields=['status']),
        ]


class Assignee(models.Model):
    date = models.DateField(_('Date'), null=True, blank=True, auto_now=True)
    user = models.ForeignKey(User, blank=True, null=True, on_delete=models.SET_NULL)
    task = models.CharField(_("Task"), max_length=255, null=True, blank=True)

    class Meta:

        indexes = [
            models.Index(fields=['date']),
            models.Index(fields=['user']),
            models.Index(fields=['task']),
        ]


class Package(CommonControlField):
    file = models.FileField(_('Package File'), null=False, blank=False)
    signature = models.CharField(_('Signature'), max_length=32, null=True, blank=True)
    category = models.CharField(_('Category'), max_length=32, choices=choices.PACKAGE_CATEGORY, null=False, blank=False)
    status = models.CharField(_('Status'), max_length=32, choices=choices.PACKAGE_STATUS, default=choices.PS_ENQUEUED_FOR_VALIDATION)
    article = models.ForeignKey(Article, blank=True, null=True, on_delete=models.SET_NULL)
    issue = models.ForeignKey(Issue, blank=True, null=True, on_delete=models.SET_NULL)
    assignee = models.ForeignKey(User, blank=True, null=True, on_delete=models.SET_NULL)
    expiration_date = models.DateField(_('Expiration date'), null=True, blank=True)

    autocomplete_search_field = 'file'

    def autocomplete_label(self):
        return f'{self.file.name} - {self.category} - {self.article or self.issue} ({self.status})'

    panels = [
        FieldPanel('file'),
        FieldPanel('category'),
        AutocompletePanel('article'),
        AutocompletePanel('issue'),
    ]

    def __str__(self):
        return self.file.name

    def save(self, *args, **kwargs):
        self.expiration_date = date.today() + timedelta(days=30)
        super(Package, self).save(*args, **kwargs)

    def files_list(self):
        files = {'files': []}

        try:
            files.update({'files': file_utils.get_file_list_from_zip(self.file.path)})
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


class ArticlePkg(CommonControlField):
    received_zip_file = models.ForeignKey(MinioFile, _('Received Zip File'), null=False, blank=False, related_name='received_zip_file')
    optimized_zip_file = models.ForeignKey(MinioFile, _('Optimized Zip File'), null=False, blank=False, related_name='optimized_zip_file')
    category = models.CharField(_('Category'), max_length=32, choices=choices.PACKAGE_CATEGORY, null=False, blank=False)
    assignee_hist = models.ManyToManyField(User)
    status_hist = models.ManyToManyField(Event)
    v3 = models.CharField(_('PID v3'), max_length=23, null=True, blank=True)

    @property
    def signature(self):
        return received_zip_file.remote_file.finger_print

    class Meta:

        indexes = [
            models.Index(fields=['v3']),
            models.Index(fields=['category']),
            models.Index(fields=['assignee_hist']),
            models.Index(fields=['status_hist']),
        ]

    @classmethod
    def check_ingress_permission(cls, v3):
        latest = ArticlePkg.objects.filter(v3=registered['v3']).latest("updated")
        if latest:
            latest_event = latest.status_hist.latest("updated")
            # TODO
            if latest_event.status in ('ERRATA_REQUIRED', 'UPDATE_REQUIRED'):
                return True
            return False
        return True


class Ingress(CommonControlField):
    v3 = models.CharField(_('PID v3'), max_length=23, null=True, blank=True)
    intents = models.ManyToManyField(ArticlePkg)
    expiration_date = models.DateField(_('Expiration date'), null=True, blank=True)

    class Meta:

        indexes = [
            models.Index(fields=['v3']),
            models.Index(fields=['intents']),
            models.Index(fields=['expiration_date']),
        ]

    @classmethod
    def start(cls, v3, creator=None, days_to_expiration=30):
        obj = cls()
        obj.v3 = v3
        obj.creator = creator
        obj.expiration_date = date.today() + timedelta(days=days_to_expiration)
        obj.save()
        return obj

    @classmethod
    def check_permission(cls, xml_article_register, zip_file_path):
        # TODO
        # verifica se está registrado
        # verifica se está esperando atualização ou correção (errata)
        # verifica se conteúdo é de atualização ou correção
        pass


class QAPackage(Package):
    class Meta:
        proxy = True


class ValidationResult(models.Model):
    id = models.AutoField(primary_key=True)
    category = models.CharField(_('Error category'), max_length=64, choices=choices.VALIDATION_ERROR_CATEGORY, null=False, blank=False)
    data = models.JSONField(_('Error data'), default=dict, null=True, blank=True)
    message = models.CharField(_('Error message'), max_length=512, null=True, blank=True)
    status = models.CharField(_('Status'), max_length=16, choices=choices.VALIDATION_STATUS, null=True, blank=True)

    package = models.ForeignKey('Package', on_delete=models.CASCADE, null=False, blank=False)

    def __str__(self):
        return '-'.join([
            str(self.id),
            self.package.file.name,
            self.category,
            self.status,
        ])

    def report_name(self):
        return choices.VALIDATION_DICT_ERROR_CATEGORY_TO_REPORT[self.category]
    
    panels = [
        MultiFieldPanel(
            [
                AutocompletePanel('package'),
                FieldPanel('category'),
            ],
            heading=_('Identification'),
            classname='collapsible'
        ),
        MultiFieldPanel(
            [
                FieldPanel('status'),
                FieldPanel('data'),
                FieldPanel('message'),
            ],
            heading=_('Content'),
            classname='collapsible'
        ),
    ]

    class Meta:
        permissions = (
            (SEND_VALIDATION_ERROR_RESOLUTION, _("Can send error resolution")),
            (ANALYSE_VALIDATION_ERROR_RESOLUTION, _("Can analyse error resolution")),
        )

    base_form_class = ValidationResultForm


class ErrorResolution(CommonControlField):
    validation_result = models.OneToOneField('ValidationResult', to_field='id', primary_key=True, related_name='resolution', on_delete=models.CASCADE)
    action = models.CharField(_('Action'), max_length=32, choices=choices.ERROR_RESOLUTION_ACTION, null=True, blank=True)
    rationale = models.TextField(_('Rationale'), max_length=512, null=True, blank=True)
    
    panels = [
        FieldPanel('action'),
        FieldPanel('rationale'),
    ]


class ErrorResolutionOpinion(CommonControlField):
    validation_result = models.OneToOneField('ValidationResult', to_field='id', primary_key=True, related_name='analysis', on_delete=models.CASCADE)
    opinion = models.CharField(_('Opinion'), max_length=32, choices=choices.ERROR_RESOLUTION_OPINION, null=True, blank=True)
    guidance = models.TextField(_('Guidance'), max_length=512, null=True, blank=True)

    panels = [
        FieldPanel('opinion'),
        FieldPanel('guidance'),
    ]
