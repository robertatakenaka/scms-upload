import os
import logging

from django.db import models
from django.utils.translation import gettext_lazy as _
from wagtail.admin.edit_handlers import (
    FieldPanel,
)
from core.models import CommonControlField, Language
from core.forms import CoreAdminModelForm
from . import exceptions


class MinioFile(CommonControlField):
    basename = models.URLField(_('Basename'), max_length=255, null=True, blank=True)
    uri = models.URLField(_('URI'), max_length=255, null=True, blank=True)
    finger_print = models.CharField('Finger print', max_length=64, null=True, blank=True)

    class Meta:

        indexes = [
            models.Index(fields=['basename']),
            models.Index(fields=['creator']),
            models.Index(fields=['created']),
            models.Index(fields=['finger_print']),
        ]

    def __str__(self):
        return f"{self.uri} {self.created}"

    @classmethod
    def get_or_create(cls, creator, uri, finger_print=None, basename=None):
        try:
            if finger_print:
                return cls.objects.get(finger_print=finger_print)
            else:
                return cls.create(creator, uri, finger_print, basename)
        except cls.DoesNotExist:
            return cls.create(creator, uri, finger_print, basename)
        except Exception as e:
            raise exceptions.MinioFileCreateError(
                "Unable to create file: %s %s %s" %
                (type(e), e, obj)
            )

    @classmethod
    def create(cls, creator, uri, finger_print=None, basename=None):
        try:
            obj = cls()
            obj.creator = creator
            obj.uri = uri
            obj.basename = basename
            obj.finger_print = finger_print
            obj.save()
            return obj
        except Exception as e:
            raise exceptions.MinioFileCreateError(
                "Unable to create file: %s %s %s" %
                (type(e), e, obj)
            )


class MinioConfiguration(CommonControlField):

    name = models.CharField(
        _('Name'), max_length=255, null=True, blank=False)
    host = models.CharField(
        _('Host'), max_length=255, null=True, blank=True)
    bucket_root = models.CharField(
        _('Bucket root'), max_length=255, null=True, blank=True)
    bucket_app_subdir = models.CharField(
        _('Bucket app subdir'), max_length=64, null=True, blank=True)
    access_key = models.CharField(
        _('Access key'), max_length=255, null=True, blank=True)
    secret_key = models.CharField(
        _('Secret key'), max_length=255, null=True, blank=True)
    secure = models.BooleanField(_('Secure'), default=True)

    class Meta:
        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['host']),
            models.Index(fields=['bucket_root']),
            models.Index(fields=['bucket_app_subdir']),
        ]

    panels = [
        FieldPanel('name'),
        FieldPanel('host'),
        FieldPanel('bucket_root'),
        FieldPanel('bucket_app_subdir'),
        FieldPanel('access_key'),
        FieldPanel('secret_key'),
        FieldPanel('secure'),
    ]

    base_form_class = CoreAdminModelForm

    def __str__(self):
        return f"{self.host} {self.bucket_root}"

    @classmethod
    def get_or_create(
            cls,
            name, host=None,
            access_key=None, secret_key=None, secure=None,
            bucket_root=None, bucket_app_subdir=None,
            user=None,
            ):
        try:
            return cls.objects.get(name=name)
        except cls.DoesNotExist:
            files_storage = cls()
            files_storage.name = name
            files_storage.host = host
            files_storage.secure = secure
            files_storage.access_key = access_key
            files_storage.secret_key = secret_key
            files_storage.bucket_root = bucket_root
            files_storage.bucket_app_subdir = bucket_app_subdir
            files_storage.creator = user
            files_storage.save()
            return files_storage

        raise exceptions.GetMinioConfigurationConfigurationError(
            f"There is no files storage which name = {name}"
        )


class SciELOFile(CommonControlField):
    pkg_name = models.CharField(_('Package name'), max_length=65, null=True, blank=True)
    relative_path = models.CharField(_('Relative Path'), max_length=255, null=True, blank=True)
    remote_file = models.ForeignKey(MinioFile, null=True, blank=True, on_delete=models.SET_NULL)
    langs = models.ManyToManyField(Language)

    class Meta:
        indexes = [
            models.Index(fields=['pkg_name']),
            models.Index(fields=['relative_path']),
            models.Index(fields=['remote_file']),
        ]

    @property
    def name(self):
        return (
            self.remote_file and self.remote_file.basename or
            os.path.basename(self.relative_path))

    @property
    def uri(self):
        if self.remote_file:
            return self.remote_file.uri

    def __str__(self):
        return self.relative_path or str(self.remote_file)

    @classmethod
    def get_or_create(cls, item, creator):
        try:
            return cls.objects.get(relative_path=item['relative_path'])
        except cls.DoesNotExist:
            file = cls()
            logging.info(item)
            file.pkg_name = item.get("key") or item.get("pkg_name")
            file.relative_path = item['relative_path']
            file.creator = creator
            file.save()
            return file

    @classmethod
    def create_or_update(cls, item, push_file, subdirs, preserve_name, creator):
        logging.info(item)
        obj = cls.get_or_create(item, creator)

        response = push_file(
            obj,
            item['path'],
            subdirs,
            preserve_name,
            creator,
        )
        logging.info(response)

        return obj


class FileWithLang(SciELOFile):

    lang = models.ForeignKey(Language, null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return f"{super()} {self.lang}"

    class Meta:
        indexes = [
            models.Index(fields=['lang']),
        ]

    @classmethod
    def get_or_create(cls, item, creator):
        logging.info("FileWithLang.get_or_create %s" % item)
        try:
            return cls.objects.get(relative_path=item['relative_path'])
        except cls.DoesNotExist:
            file = cls()
            logging.info(item)
            file.pkg_name = item.get("key") or item.get("pkg_name")
            try:
                code2 = item['lang']
                file.lang = Language.get_or_create(
                    code2=code2, creator=creator)
            except KeyError:
                code2 = None
            file.relative_path = item['relative_path']
            file.creator = creator
            file.save()
            return file


class AssetFile(SciELOFile):
    is_supplementary_material = models.BooleanField(default=False)

    def __str__(self):
        return f"{super()} {self.is_supplementary_material}"

    class Meta:
        indexes = [
            models.Index(fields=['is_supplementary_material']),
        ]


class XMLFile(FileWithLang):
    assets_files = models.ManyToManyField(AssetFile)

    def __str__(self):
        return f"{super()}"


class BodyAndBackXMLFile(XMLFile):
    selected = models.BooleanField(default=False)
    version = models.IntegerField(_("Version"), null=True, blank=True)

    def __str__(self):
        return f"{super()} {self.version} {self.selected}"


class SciELOHTMLFile(FileWithLang):
    part = models.CharField(
        _('Part'), max_length=6, null=False, blank=False)
    assets_files = models.ManyToManyField(AssetFile)

    class Meta:

        indexes = [
            models.Index(fields=['part']),
        ]

    def __str__(self):
        return f"{super()} {self.part}"

    @classmethod
    def get_or_create(cls, item, creator):
        try:
            return cls.objects.get(relative_path=item['relative_path'])
        except cls.DoesNotExist:
            file = cls()
            logging.info(item)
            file.pkg_name = item.get("key") or item.get("pkg_name")
            file.lang = Language.get_or_create(code2=item['lang'], creator=creator)
            file.part = item['part']
            file.relative_path = item['relative_path']
            file.creator = creator
            file.save()
            return file

    @property
    def text(self):
        try:
            response = requests.get(self.uri, timeout=10)
        except Exception as e:
            return "Unable to get text from {}".format(self.uri)
        else:
            return response.content
