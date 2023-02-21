import os
import json
import logging
from tempfile import TemporaryDirectory

import requests
from requests.auth import HTTPBasicAuth
from django.contrib.auth import get_user_model
from django.utils.translation import gettext as _
from config.settings.base import (
    API_PID_PROVIDER_URI,
    API_PID_PROVIDER_TOKEN_URI,
)

from files_storage.controller import FilesStorageManager
from xmlsps import xml_sps_lib
from pid_provider.models import XMLDocPid
from . import exceptions


User = get_user_model()

LOGGER = logging.getLogger(__name__)
LOGGER_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


class ArticleXMLRegistration:
    """
    Faz registro de pid local e central, mantém os registros sincronizados
    """
    def __init__(self):
        # para PidProvider local, files_storage_name == 'website'
        self.local_pid_provider = PidProvider(files_storage_name='website')
        self.api_uri = API_PID_PROVIDER_URI
        self.api_token_uri = API_PID_PROVIDER_TOKEN_URI
        self.timeout = 15

    def register(self, xml_with_pre, name, user):
        registered = self._request_pid_v3(xml_with_pre, name, user)
        return registered

    def register_xml_uri(self, xml_uri, name, user):
        xml_with_pre = xml_sps_lib.get_xml_with_pre_from_uri(xml_uri)
        registered = self._request_pid_v3(xml_with_pre, name, user)
        return registered

    def register_xml_zip(self, zip_xml_file_path, user, synchronized=None):
        """
        Returns
        -------
            list of dict
                {"filename": filename,
                 registered": dict (XMLDocPid.data),
                 "xml_changed": boolean}
        """
        for item in xml_sps_lib.get_xml_items(zip_xml_file_path):
            xml_with_pre = item.pop("xml_with_pre")
            registered = self._request_pid_v3(
                xml_with_pre, item["filename"], user, synchronized,
            )
            item.update(registered or {})
            yield item

    def _request_pid_v3(self, xml_with_pre, name, user):
        """
        Realiza os registros local e remoto de acordo com a necessidade
        """
        # verifica a necessidade de registro
        demand = XMLDocPid.get_registration_demand(xml_with_pre)

        logging.info(demand)
        registered = demand['registered']
        required_local = demand['required_local']
        required_remote = demand['required_remote']

        if not required_local and not required_remote:
            # não é necessário registrar, retornar os dados atuais
            return registered

        api_response = None

        if required_remote and self.api_uri:
            # TODO remover o tratamento de exceção
            try:
                api_response = self._register_in_core(xml_with_pre, name, user)
                logging.info("api_response=%s" % api_response)
            except exceptions.APIPidProviderPostError as e:
                logging.exception(e)

        if required_local:
            # realizar registro local
            if api_response:
                xml_with_pre = xml_sps_lib.get_xml_with_pre_from_uri(
                    api_response["xml_uri"])
            return self.local_pid_provider.register(
                    xml_with_pre, name, user, synchronized=bool(api_response))
        else:
            # não precisa fazer registro local, retorna os dados atuais
            return registered

    def _register_in_core(self, xml_with_pre, name, user):
        """
        name : str
            nome do arquivo xml
        """
        with TemporaryDirectory() as tmpdirname:
            name, ext = os.path.splitext(name)
            zip_xml_file_path = os.path.join(tmpdirname, name + ".zip")

            xml_sps_lib.create_xml_zip_file(
                zip_xml_file_path, xml_with_pre.tostring())

            response = self._api_request_post(
                zip_xml_file_path, user, self.timeout)

            for item in response:
                try:
                    return item['registered']
                except KeyError:
                    return item

    def _api_request_post(self, zip_xml_file_path, user, timeout):
        # TODO retry
        """
        curl -X POST -S \
            -H "Content-Disposition: attachment;filename=pacote_xml.zip" \
            -F "file=@/path/pacote_xml.zip;type=application/zip" \
            --user "adm:adm" \
            127.0.0.1:8000/pid_provider/
        """
        try:
            # token = self._get_token(user, timeout)
            # logging.info(token)
            auth = HTTPBasicAuth(user.username, 'adm')
            basename = os.path.basename(zip_xml_file_path)
            file_info = (
                basename,
                open(zip_xml_file_path, 'rb'),
                'application/zip',
            )
            files = {
                'file':
                file_info
            }
            header = {
                'content-type': 'multi-part/form-data',
                'Content-Disposition': 'attachment; filename=%s' % basename,
            }
            response = requests.post(
                self.api_uri,
                files=files,
                headers=header,
                auth=auth,
                timeout=timeout,
                verify=False,
            )
            return json.loads(response.text)
        except Exception as e:
            logging.exception(e)
            raise exceptions.APIPidProviderPostError(
                _("Unable to request pid to central pid provider {} {} {}").format(
                    zip_xml_file_path, type(e), e,
                )
            )

    def _get_token(self, user, timeout):
        """
        curl -X POST 127.0.0.1:8000/api-token-auth/ \
            --data 'username=x&password=x'
        """
        try:
            auth = HTTPBasicAuth('adm', 'adm')
            logging.info(self.api_token_uri)
            username = 'adm'
            password = 'adm'
            response = requests.post(
                self.api_token_uri,
                data={'username': username, "password": password},
                auth=auth,
                timeout=timeout,
            )
            logging.info(type(response))
            logging.info(str(response))
            logging.info(response.text)
            logging.info(response.content)
            logging.info(type(response.content))

            return response.json
        except Exception as e:
            # TODO tratar as exceções
            raise exceptions.GetAPITokenError(
                _("Unable to get api token {} {} {}").format(
                    user, type(e), e,
                )
            )

    def synchronize(self):
        """
        Identifica no pid provider local os registros que não
        estão sincronizados com o pid provider remoto (central) e
        faz a sincronização, registrando o XML local no pid provider remoto
        """
        if not self.api_uri:
            raise ValueError(
                _("Unable to synchronized data with central pid provider because API URI is missing")
            )
        for item in XMLDocPid.unsynchronized:
            try:
                xml_with_pre = xml_sps_lib.get_xml_with_pre_from_uri(
                    item.xml_uri)
                name = os.path.basename(item.xml_uri)
                response = self._register_in_core(
                    xml_with_pre, name, item.creator)
                logging.info(response)
                if response and response.get("xml_uri"):
                    # muda status para sincronizado
                    item.set_synchronized(True)
            except Exception as e:
                item.failure = SyncFailure.create(
                    _("Unable to do remote pid registration {} {} {}").format(
                        name, type(e), e,
                    ),
                    e, item.creator
                )
                item.save()


class PidProvider:
    """
    Registra XMLDocPid local ou remoto
    """
    def __init__(self, files_storage_name):
        self.files_storage_manager = FilesStorageManager(files_storage_name)

    @classmethod
    def get_xml_uri(self, v3):
        return XMLDocPid.get_xml_uri(v3)

    def register(self, xml_with_pre, filename, user, synchronized=None):
        """
        Returns
        -------
            dict or None
                {"registered": dict (XMLDocPid.data), "xml_changed": boolean}
        """
        return XMLDocPid.register(
            xml_with_pre, filename, user,
            self.files_storage_manager.push_pid_provider_xml,
            synchronized,
        )

    def register_xml_zip(self, zip_xml_file_path, user, synchronized=None):
        """
        Returns
        -------
            list of dict
                {"filename": filename,
                 registered": dict (XMLDocPid.data),
                 "xml_changed": boolean}
        """
        for item in xml_sps_lib.get_xml_items(zip_xml_file_path):
            xml_with_pre = item.pop("xml_with_pre")
            # {"filename": item: "xml": xml}
            registered = self.register(
                xml_with_pre, item["filename"], user, synchronized,
            )
            item.update(registered or {})
            yield item

    def register_xml_uri(self, xml_uri, filename, user, synchronized=None):
        """
        Returns
        -------
            dict or None
                {"registered": dict (XMLDocPid.data), "xml_changed": boolean}
        """
        xml_with_pre = xml_sps_lib.get_xml_with_pre_from_uri(xml_uri)
        return self.register(xml_with_pre, filename, user, synchronized)

    @classmethod
    def get_registered(cls, xml_with_pre):
        """
        Returns
        -------
            None or XMLDocPid.data (dict)
        """
        return XMLDocPid.get_registered(xml_with_pre)

    @classmethod
    def get_registered_xml_uri(cls, xml_uri):
        """
        Returns
        -------
            None or XMLDocPid.data (dict)
        """
        xml_with_pre = xml_sps_lib.get_xml_with_pre_from_uri(xml_uri)
        return cls.get_registered(xml_with_pre)

    @classmethod
    def get_registered_xml_zip(cls, zip_xml_file_path):
        """
        Returns
        -------
            list of dict
                {"filename": filename,
                 "registered": dict (XMLDocPid.data)}
        """
        for item in xml_sps_lib.get_xml_items(zip_xml_file_path):
            # {"filename": item: "xml": xml}
            registered = cls.get_registered(item['xml_with_pre'])
            if registered:
                item['registered'] = registered
