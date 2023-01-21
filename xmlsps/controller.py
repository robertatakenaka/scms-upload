import os
import logging
from tempfile import TemporaryDirectory

import requests
from requests.auth import HTTPBasicAuth
from django.contrib.auth import get_user_model
from django.utils.translation import gettext as _

from files_storage.controller import FilesStorageManager
from xmlsps import xml_sps_lib
from .models import EncodedXMLArticle
from . import exceptions


User = get_user_model()

LOGGER = logging.getLogger(__name__)
LOGGER_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


class XMLArticleRegister:
    """
    Faz registro do XML local e remotamente, mantém os registros sincronizados
    """
    def __init__(self, files_storage_name, pid_provider_api_uri=None, timeout=None):
        self._pid_requester = PidRequester(
            files_storage_name, pid_provider_api_uri, timeout)

    def register(self, xml_with_pre, name, user):
        """
        Realiza os registros local e remoto de acordo com a necessidade
        """
        return self._pid_requester.request_pids(xml_with_pre, name, user)

    def register_for_xml_uri(self, xml_uri, name, user):
        return self._pid_requester.request_pids_for_xml_uri(
            xml_uri, name, user)

    def get_registered(self, xml_with_pre):
        return self._pid_requester.local_pid_provider.get_registered(
            xml_with_pre)

    def get_registered_for_xml_zip(self, zip_xml_file_path):
        return self._pid_requester.local_pid_provider.get_registered_for_xml_zip(
            zip_xml_file_path)

    def get_registered_for_xml_uri(self, xml_uri):
        return self._pid_requester.local_pid_provider.get_registered_for_xml_uri(
            xml_uri)

    def get_xml_uri(self, v3):
        return self._pid_requester.local_pid_provider.get_xml_uri(v3)


class PidRequester:
    """
    Faz registro de pid local e remotamente, mantém os registros sincronizados
    """
    def __init__(self, files_storage_name, api_uri=None, timeout=None):
        self.local_pid_provider = PidProvider(files_storage_name)
        url = api_uri[:-1]
        url = url[:url.rfind("/")]
        self.api_uri = api_uri
        self.api_uri_token = f"{url}/api-token-auth/"
        self.timeout = timeout or 15

    def get_registration_demand(self, xml_with_pre):
        """
        Verifica se há necessidade de registrar local e/ou remotamente
        """
        do_remote_registration = True
        do_local_registration = True

        registered, equal = self.local_pid_provider.is_registered_and_equal(
            xml_with_pre)
        if registered:
            if equal:
                # skip local registration
                do_local_registration = False
                do_remote_registration = not registered['synchronized']
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
        for item in self.local_pid_provider.get_items_to_synchronize:
            try:
                xml_with_pre = xml_sps_lib.get_xml_with_pre_from_uri(
                    item.xml_uri)
                name = os.path.basename(item.xml_uri)
                response = self._api_provide_pids(
                    xml_with_pre, name, item.creator)
                logging.info(response)
                if response and response.get("xml_uri"):
                    # muda status para sincronizado
                    item.set_synchronized(True)
            except Exception as e:
                logging.exception(
                    _("Unable to do remote pid registration {} {} {}").format(
                        name, type(e), e,
                    )
                )

    def request_pids(self, xml_with_pre, name, user):
        """
        Realiza os registros local e remoto de acordo com a necessidade
        """
        # verifica a necessidade de registro
        demand = self.get_registration_demand(xml_with_pre)
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
                api_response = self._api_provide_pids(
                    xml_with_pre, name, user)
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
            # FIXME exceção?
            if api_response:
                xml_with_pre = xml_sps_lib.get_xml_with_pre_from_uri(
                    api_response["xml_uri"])
            return self.local_pid_provider.provide_pids(
                    xml_with_pre, name, user, synchronized=bool(api_response))
        else:
            # não precisa fazer registro local, retorna os dados atuais
            return registered

    def _api_provide_pids(self, xml_with_pre, name, user):
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
                # headers={'Authorization': f"Token {token['token']}"},
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
            logging.info(self.api_uri_token)
            return requests.post(
                self.api_uri_token,
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

    def request_pids_for_xml_uri(self, xml_uri, name, user):
        xml_with_pre = xml_sps_lib.get_xml_with_pre_from_uri(xml_uri)
        return self.request_pids(xml_with_pre, name, user)


class PidProvider:
    """
    Registra EncodedXMLArticle local ou remoto
    """
    def __init__(self, files_storage_name):
        self.files_storage_manager = FilesStorageManager(files_storage_name)

    def is_registered_and_equal(self, xml_with_pre):
        return EncodedXMLArticle.is_registered_and_equal(xml_with_pre)

    def get_xml_uri(self, v3):
        return EncodedXMLArticle.get_xml_uri(v3)

    def provide_pids(self, xml_with_pre, filename, user, synchronized=None):
        return EncodedXMLArticle.provide_pids(
            xml_with_pre, filename, user,
            self.files_storage_manager.register_pid_provider_xml,
            synchronized,
        )

    def provide_pids_for_xml_zip(self, zip_xml_file_path, user, synchronized=None):
        try:
            logging.info("provide_pids_for_xml_zip")
            logging.info(os.path.isfile(zip_xml_file_path))
            items = []
            for item in xml_sps_lib.get_xml_items(zip_xml_file_path):
                xml_with_pre = item.pop("xml_with_pre")
                logging.info(item)
                try:
                    # {"filename": item: "xml": xml}
                    registered = self.provide_pids(
                        xml_with_pre, item["filename"], user,
                        synchronized,
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
            return items
        except Exception as e:
            logging.exception(e)
            raise exceptions.RequestDocumentIDsForXMLZipFileError(
                _("Unable to request document IDs for {} {} {}").format(
                    zip_xml_file_path, type(e), e,
                )
            )

    def provide_pids_for_xml_uri(self, xml_uri, filename, user, synchronized=None):
        try:
            xml_with_pre = xml_sps_lib.get_xml_with_pre_from_uri(xml_uri)
            return self.provide_pids(
                xml_with_pre, filename, user, synchronized
            )
        except Exception as e:
            logging.exception(e)
            raise exceptions.RequestDocumentIDsForXMLUriError(
                _("Unable to request document ids for xml uri {} {} {}").format(
                    xml_uri, type(e), e,
                )
            )

    def get_registered(self, xml_with_pre):
        return EncodedXMLArticle.get_registered(xml_with_pre)

    def get_registered_for_xml_zip(self, zip_xml_file_path):
        try:
            for item in xml_sps_lib.get_xml_items(zip_xml_file_path):
                try:
                    # {"filename": item: "xml": xml}
                    registered = self.get_registered(item['xml_with_pre'])
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
        except Exception as e:
            logging.exception(e)
            raise exceptions.GetRegisteredXMLZipError(
                _("Unable to get registered XML for {} {} {}").format(
                    zip_xml_file_path, type(e), e,
                )
            )

    def get_registered_for_xml_uri(self, xml_uri):
        try:
            xml_with_pre = xml_sps_lib.get_xml_with_pre_from_uri(xml_uri)
            return self.get_registered(xml_with_pre)
        except Exception as e:
            logging.exception(e)
            raise exceptions.GetRegisteredXMLUriError(
                _("Unable to get registered xml uri {} {} {}").format(
                    xml_uri, type(e), e,
                )
            )

    @property
    def get_items_to_synchronize(self):
        """
        Identifica no pid provider local os registros que não
        estão sincronizados com o pid provider remoto (central) e
        faz a sincronização, registrando o XML local no pid provider remoto
        """
        return EncodedXMLArticle.objects.filter(synchronized=False).iterator()
