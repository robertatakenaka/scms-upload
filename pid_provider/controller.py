import os
import logging
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import requests
from requests.auth import HTTPBasicAuth
from django.utils.translation import gettext as _

from files_storage.controller import FilesStorageManager
from core.libs import xml_sps_lib
from .models import PidV3


LOGGER = logging.getLogger(__name__)
LOGGER_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


class PidRequester:

    def __init__(self, files_storage_name, api_uri=None, timeout=None):
        self.local_pid_provider = PidProvider(files_storage_name)
        self.api_uri = api_uri
        self.timeout = timeout or 15

    def request_doc_ids(self, xml_with_pre, name, user):
        response = None
        if self.api_uri:
            response = self._api_request_doc_ids(xml_with_pre, name, user)

        if response:
            result = self.local_pid_provider.request_document_ids_for_xml_uri(
                response["xml_uri"], name, user)
        else:
            result = self.local_pid_provider.request_document_ids(
                xml_with_pre, name, user)

        if result:
            return {
                "v3": result['registered'].v3,
                "xml_changed": result['xml_changed'],
                "xml_uri": result['registered'].xml_uri,
            }

    def _api_request_doc_ids(self, xml_with_pre, name, user):
        """
        name : str
            nome do arquivo xml
        """

        with TemporaryDirectory() as tmpdirname:
            zip_xml_file_path = os.path.join(tmpdirname, name + ".zip")

            xml_filename = name
            name, ext = os.path.splitext(xml_filename)

            with ZipFile(zip_xml_file_path, "w") as zf:
                zf.writestr(xml_filename, xml_with_pre.tostring())

            with open(zip_xml_file_path, "rb") as fp:
                # {"v3": v3, "xml_uri": xml_uri}
                return self._api_request_post(
                    fp, xml_filename, user, self.timeout)

    def _api_request_post(self, fp, xml_filename, user, timeout):
        # TODO retry
        try:
            auth = HTTPBasicAuth(user.name, user.password)
            return requests.post(
                self.api_uri,
                files={"zip_xml_file_path": fp},
                auth=auth,
                timeout=timeout,
            )
        except Exception as e:
            # TODO tratar as exceções
            logging.exception(e)

    def request_doc_ids_for_xml_uri(self, xml_uri, name, user):
        xml_with_pre = xml_sps_lib.get_xml_with_pre_from_uri(xml_uri)
        return self.request_doc_ids(xml_with_pre, name, user)


class PidProvider:

    def __init__(self, files_storage_name):
        self.files_storage_manager = FilesStorageManager(files_storage_name)

    def request_document_ids(self, xml_with_pre, filename, user):
        return PidV3.request_document_ids(
            xml_with_pre, filename, user,
            self.files_storage_manager.register_pid_provider_xml,
        )

    def request_document_ids_for_xml_zip(self, zip_xml_file_path, user):
        return PidV3.request_document_ids_for_xml_zip(
            zip_xml_file_path, user,
            self.files_storage_manager.register_pid_provider_xml,
        )

    def request_document_ids_for_xml_uri(self, xml_uri, filename, user):
        return PidV3.request_document_ids_for_xml_uri(
            xml_uri, filename, user,
            self.files_storage_manager.register_pid_provider_xml,
        )

    def get_registered(self, xml_with_pre):
        return PidV3.get_registered(xml_with_pre)

    def get_registered_xml_zip(self, zip_xml_file_path):
        return PidV3.get_registered_xml_zip(zip_xml_file_path)

    def get_registered_xml_uri(self, xml_uri):
        return PidV3.get_registered_xml_uri(xml_uri)
