from django.contrib.auth import get_user_model
from django.db import models
from django.utils.translation import gettext_lazy as _

from xmlsps.controller import XMLArticleRegister
from core.models import CommonControlField
from . import choices


User = get_user_model()
xml_article_register = XMLArticleRegister()


class PublicationArticle(CommonControlField):

    v3 = models.CharField(_('PID v3'), max_length=23, blank=True, null=True)
    status = models.CharField(
        _('Publication status'), max_length=20,
        blank=True, null=True, choices=choices.PUBLICATION_STATUS)

    @property
    def xml_uri(self):
        return XMLArticleRegister.get_xml_uri(self.v3)

    def register(self, xml_with_pre, name, user):
        """
        Realiza os registros local e remoto de acordo com a necessidade
        """
        response = xml_article_register.register(xml_with_pre, name, user)
        self.v3 = response['registered']['v3']
        return response

    def register_for_xml_uri(self, xml_uri, name, user):
        response = xml_article_register.request_pids_for_xml_uri(
            xml_uri, name, user)
        self.v3 = response['registered']['v3']
        return response

    def request_pids_for_xml_zip(self, zip_file_path, name, user):
        response = xml_article_register.request_pids_for_xml_zip(
            zip_file_path, name, user)
        for item in response:
            self.v3 = item['registered']['v3']
        return response

    @classmethod
    def get_registered(cls, xml_with_pre):
        return XMLArticleRegister.get_registered(xml_with_pre)

    @classmethod
    def get_registered_for_xml_zip(cls, zip_xml_file_path):
        return XMLArticleRegister.get_registered_for_xml_zip(
            zip_xml_file_path)

    @classmethod
    def get_registered_for_xml_uri(cls, xml_uri):
        return XMLArticleRegister.get_registered_for_xml_uri(xml_uri)

    @classmethod
    def get_xml_uri(self, v3):
        return XMLArticleRegister.get_xml_uri(v3)

    def update_status(self, user, status):
        self.status = status
        self.updated_by = user
        self.save()
