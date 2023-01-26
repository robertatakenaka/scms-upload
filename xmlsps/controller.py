import os
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
from .models import XMLDocPid
from . import exceptions


User = get_user_model()

LOGGER = logging.getLogger(__name__)
LOGGER_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


class PidRequester:
    """
    Faz registro de pid local e central, mantém os registros sincronizados
    """
    def __init__(self):
        self.local_pid_provider = PidProvider(files_storage_name='website')
        self.api_uri = API_PID_PROVIDER_URI
        self.api_token_uri = API_PID_PROVIDER_TOKEN_URI
        self.timeout = 15

    def register_for_xml_uri(self, xml_uri, name, user):
        xml_with_pre = xml_sps_lib.get_xml_with_pre_from_uri(xml_uri)
        return self.register(xml_with_pre, name, user)

    def register(self, xml_with_pre, name, user):
        """
        Realiza os registros local e remoto de acordo com a necessidade
        """
        # verifica a necessidade de registro
        demand = XMLDocPid.get_registration_demand(xml_with_pre)
        logging.info(demand)
        registered = demand['registered']
        do_local_registration = demand['do_local_registration']
        do_remote_registration = demand['do_remote_registration']

        if not do_local_registration and not do_remote_registration:
            # não é necessário registrar, retornar os dados atuais
            return registered

        api_response = None
        logging.info((do_remote_registration, self.api_uri))
        if do_remote_registration and self.api_uri:
            # realizar registro remoto
            try:
                api_response = self._register_in_core(xml_with_pre, name, user)
                logging.info(api_response)
            except Exception as e:
                logging.exception(
                    _("Unable to do remote pid registration {} {} {}").format(
                        name, type(e), e)
                )
                raise exceptions.APIPidProviderPostError(
                    _("Unable to request pid to central pid provider {} {} {}").format(
                        name, type(e), e,
                    )
                )

        if do_local_registration:
            # realizar registro local
            if api_response:
                xml_with_pre = xml_sps_lib.get_xml_with_pre_from_uri(
                    api_response["xml_uri"])
            return self.local_pid_provider.register(
                    xml_with_pre, name, user, synchronized=bool(api_response))
        else:
            # não precisa fazer registro local, retorna os dados atuais
            return registered

    def register_for_xml_zip(self, zip_xml_file_path, user, synchronized=None):
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
            try:
                registered = self.register(
                    xml_with_pre, item["filename"], user, synchronized,
                )
                if registered:
                    item.update(registered)
                logging.info(item)
                yield item
            except Exception as e:
                logging.exception(e)
                item['error'] = (
                    _("Unable to request document IDs for {} {} {} {}").format(
                        zip_xml_file_path, item['filename'], type(e), e,
                    )
                )
                yield item

    def _register_in_core(self, xml_with_pre, name, user):
        """
        name : str
            nome do arquivo xml
        """
        with TemporaryDirectory() as tmpdirname:
            zip_xml_file_path = os.path.join(tmpdirname, name + ".zip")
            xml_sps_lib.create_xml_zip_file(
                zip_xml_file_path, xml_with_pre.tostring())
            return self._api_request_post(
                zip_xml_file_path, user, self.timeout)

    def _api_request_post(self, zip_xml_file_path, user, timeout):
        # TODO retry
        """
        curl -F 'zip_xml_file_path=@4Fk4QXbF3YLW46LTwhbFh6K.xml.zip' \
           --user "adm:adm" \
           http://127.0.0.1:8000/pidv3/
        """
        try:
            # token = self._get_token(user, timeout)

            # logging.info(token)
            auth = HTTPBasicAuth(user.name, user.password)
            return requests.post(
                self.api_uri,
                files={"file": zip_xml_file_path},
                headers={'Authorization': f"Token {token['token']}"},
                auth=auth,
                timeout=timeout,
            )
        except Exception as e:
            # TODO tratar as exceções
            raise exceptions.APIPidProviderPostError(
                _("Unable to request pid to central pid provider {} {} {}").format(
                    zip_xml_file_path, type(e), e,
                )
            )

    def _get_token(self, user, timeout):
        # TODO retry
        """
        curl -X POST -F 'username="adm"' -F 'password="adm"' \
            127.0.0.1:8000/api-token-auth/
        """
        try:
            auth = HTTPBasicAuth(user.name, user.password)
            logging.info(self.api_token_uri)
            return requests.post(
                self.api_token_uri,
                data={'username': user.name, "password": user.password},
                auth=auth,
                timeout=timeout,
            )
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
            self.files_storage_manager.register_pid_provider_xml,
            synchronized,
        )

    def register_for_xml_zip(self, zip_xml_file_path, user, synchronized=None):
        """
        Returns
        -------
            list of dict
                {"filename": filename,
                 registered": dict (XMLDocPid.data),
                 "xml_changed": boolean}
        """
        items = []
        for item in xml_sps_lib.get_xml_items(zip_xml_file_path):
            xml_with_pre = item.pop("xml_with_pre")
            try:
                # {"filename": item: "xml": xml}
                registered = self.register(
                    xml_with_pre, item["filename"], user, synchronized,
                )
                if registered:
                    item.update(registered)
                yield item
            except Exception as e:
                logging.exception(e)
                item['error'] = (
                    _("Unable to request document IDs for {} {} {} {}").format(
                        zip_xml_file_path, item['filename'], type(e), e,
                    )
                )
                yield item
        return items

    def register_for_xml_uri(self, xml_uri, filename, user, synchronized=None):
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
    def get_registered_for_xml_uri(cls, xml_uri):
        """
        Returns
        -------
            None or XMLDocPid.data (dict)
        """
        xml_with_pre = xml_sps_lib.get_xml_with_pre_from_uri(xml_uri)
        return cls.get_registered(xml_with_pre)

    @classmethod
    def get_registered_for_xml_zip(cls, zip_xml_file_path):
        """
        Returns
        -------
            list of dict
                {"filename": filename,
                 "registered": dict (XMLDocPid.data)}
        """
        for item in xml_sps_lib.get_xml_items(zip_xml_file_path):
            try:
                # {"filename": item: "xml": xml}
                registered = cls.get_registered(item['xml_with_pre'])
                if registered:
                    item['registered'] = registered
                yield item
            except Exception as e:
                logging.exception(e)
                item['error'] = (
                    _("Unable to get registered XML for {} {} {} {}").format(
                        zip_xml_file_path, item['filename'], type(e), e,
                    )
                )
                yield item
