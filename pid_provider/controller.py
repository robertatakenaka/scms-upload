import os
import logging
from tempfile import TemporaryDirectory
from zipfile import ZipFile

import requests
from requests.auth import HTTPBasicAuth
from django.contrib.auth import get_user_model
from django.utils.translation import gettext as _

from files_storage.controller import FilesStorageManager
from core.libs import xml_sps_lib
from .models import PidV3
from . import exceptions


User = get_user_model()

LOGGER = logging.getLogger(__name__)
LOGGER_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


class PidRequester:

    def __init__(self, files_storage_name, api_uri=None, timeout=None):
        self.local_pid_provider = PidProvider(files_storage_name)
        self.api_uri = api_uri
        self.timeout = timeout or 15

    def get_registration_demand(self, xml_with_pre):
        """
        Verifica se há necessidade de registrar local e/ou remotamente
        """
        do_remote_registration = True
        do_local_registration = True

        registered = PidV3.get_registered(xml_with_pre)
        if registered:
            if registered.is_equal_to(xml_with_pre):
                # skip local registration
                do_local_registration = False
                if registered.synchronized:
                    # skip remote registration
                    do_remote_registration = False

        return dict(
            registered=registered,
            do_local_registration=do_local_registration,
            do_remote_registration=do_remote_registration,
        )

    def synchronize(self):
        """
        Identifica no pid provider local os registros que não
        estão sincronizados com o pid provider remoto (central) e
        faz a sincronização, registrando o XML local no pid provider remoto
        """
        for item in PidV3.objects.filter(synchronized=False).iterator():
            try:
                xml_with_pre = xml_sps_lib.get_xml_with_pre_from_uri(
                    item.xml_uri)
                name = os.path.basename(item.xml_uri)
                response = self._api_request_doc_ids(
                    xml_with_pre, name, item.creator)
                if response and response.get("xml_uri"):
                    # muda status para sincronizado
                    item.set_synchronized(True)
            except Exception as e:
                logging.exception(
                    "Unable to do remote pid registration %s %s %s" %
                    (name, type(e), e)
                )

    def request_doc_ids(self, xml_with_pre, name, user):
        """
        Realiza os registros local e remoto de acordo com a necessidade
        """
        # verifica a necessidade de registro
        demand = self.get_registration_demand(xml_with_pre)
        registered = demand['registered']
        do_local_registration = demand['do_local_registration']
        do_remote_registration = demand['do_remote_registration']

        if not do_local_registration and not do_remote_registration:
            # não é necessário registrar, retornar os dados atuais
            return {
                "v3": registered.v3,
                "xml_changed": False,
                "xml_uri": registered.xml_uri,
            }

        response = None
        if do_remote_registration and self.api_uri:
            # realizar registro remoto
            try:
                response = self._api_request_doc_ids(xml_with_pre, name, user)
            except Exception as e:
                logging.exception(
                    "Unable to do remote pid registration %s %s %s" %
                    (name, type(e), e)
                )

        if do_local_registration:
            # realizar registro local
            # FIXME exceção?
            if response:
                result = self.local_pid_provider.request_document_ids_for_xml_uri(
                    response["xml_uri"], name, user, synchronized=True)
            else:
                result = self.local_pid_provider.request_document_ids(
                    xml_with_pre, name, user, synchronized=False)

            if result:
                if result.get("error"):
                    return result
                return {
                    "v3": result['registered'].v3,
                    "xml_changed": result['xml_changed'],
                    "xml_uri": result['registered'].xml_uri,
                }
        else:
            # não precisa fazer registro local, retorna os dados atuais
            return {
                "v3": registered.v3,
                "xml_changed": False,
                "xml_uri": registered.xml_uri,
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
        """
        curl -F 'zip_xml_file_path=@4Fk4QXbF3YLW46LTwhbFh6K.xml.zip' http://127.0.0.1:8000/pidv3/
        """
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
            raise exceptions.APIPidProviderPostError(
                _("Unable to request pid to central pid provider {} {} {}").format(
                    xml_filename, type(e), e
                    ))

    def request_doc_ids_for_xml_uri(self, xml_uri, name, user):
        xml_with_pre = xml_sps_lib.get_xml_with_pre_from_uri(xml_uri)
        return self.request_doc_ids(xml_with_pre, name, user)


class PidProvider:

    def __init__(self, files_storage_name):
        self.files_storage_manager = FilesStorageManager(files_storage_name)

    def request_document_ids(self, xml_with_pre, filename, user, synchronized):
        return PidV3.request_document_ids(
            xml_with_pre, filename, user,
            self.files_storage_manager.register_pid_provider_xml,
            synchronized,
        )

    def request_document_ids_for_xml_zip(self, zip_xml_file_path, user, synchronized):
        return PidV3.request_document_ids_for_xml_zip(
            zip_xml_file_path, user,
            self.files_storage_manager.register_pid_provider_xml,
            synchronized,
        )

    def request_document_ids_for_xml_uri(self, xml_uri, filename, user, synchronized):
        return PidV3.request_document_ids_for_xml_uri(
            xml_uri, filename, user,
            self.files_storage_manager.register_pid_provider_xml,
            synchronized,
        )

    def get_registered(self, xml_with_pre):
        return PidV3.get_registered(xml_with_pre)

    def get_registered_xml_zip(self, zip_xml_file_path):
        return PidV3.get_registered_xml_zip(zip_xml_file_path)

    def get_registered_xml_uri(self, xml_uri):
        return PidV3.get_registered_xml_uri(xml_uri)
