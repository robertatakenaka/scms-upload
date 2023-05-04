import os
import logging
from tempfile import TemporaryDirectory

import requests
from requests.auth import HTTPBasicAuth
from django.contrib.auth import get_user_model
from django.utils.translation import gettext as _

from files_storage.controller import FilesStorageManager
from pid_requester.models import PidRequesterXML, SyncFailure, PidProviderConfig
from pid_requester import exceptions
from xmlsps import xml_sps_lib


User = get_user_model()

LOGGER = logging.getLogger(__name__)
LOGGER_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


class PidRequester:
    """
    Faz registro de pid local e central, mantém os registros sincronizados
    """

    def __init__(self):
        # para PidProvider local, files_storage_name == 'website'
        self.pid_registration = PidRegistration(files_storage_name="website")

        config = PidProviderConfig.get_or_create()
        self.pid_provider_api = PidProviderAPI(
            pid_provider_api_post_xml=config.pid_provider_api_post_xml,
            pid_provider_api_get_token=config.pid_provider_api_get_token,
            timeout=config.timeout,
            api_username=config.api_username,
            api_password=config.api_password,
        )

    def request_pid_for_xml_uri(self, xml_uri, name, user):
        xml_with_pre = xml_sps_lib.get_xml_with_pre_from_uri(xml_uri)
        registered = self.request_pid_for_xml_with_pre(xml_with_pre, name, user)
        return registered

    def request_pid_for_xml_zip(self, zip_xml_file_path, user, synchronized=None):
        """
        Returns
        -------
            list of dict
                {"filename": filename,
                 registered": dict (PidRequesterXML.data),
                 "xml_changed": boolean}
        """
        for item in xml_sps_lib.get_xml_items(zip_xml_file_path):
            xml_with_pre = item.pop("xml_with_pre")
            registered = self.request_pid_for_xml_with_pre(
                xml_with_pre,
                item["filename"],
                user,
                synchronized,
            )
            item.update(registered or {})
            logging.info(item)
            yield item

    def request_pid_for_xml_with_pre(self, xml_with_pre, name, user, demand=None):
        """
        Realiza os registros local e remoto de acordo com a necessidade
        """
        # verifica a necessidade de registro local e/ou remoto
        if not demand:
            demand = PidRequesterXML.get_registration_demand(xml_with_pre)
        logging.info(demand)

        response = None
        registered = demand["registered"]

        if demand["required_remote"]:
            response = self.pid_provider_api.provide_pid(xml_with_pre, name)

        if demand["required_local"]:
            registered = self.pid_registration.register_pid(
                xml_with_pre,
                name,
                user,
                synchronized=bool(
                    demand["required_remote"] or response and response.get('xml_uri')
                )
            )

        return registered

    @classmethod
    def is_registered_xml_with_pre(cls, xml_with_pre):
        """
        Returns
        -------
            {"error": ""}
            or
            {
                "v3": self.v3,
                "v2": self.v2,
                "aop_pid": self.aop_pid,
                "xml_uri": self.xml_uri,
                "article": self.article,
                "created": self.created.isoformat(),
                "updated": self.updated.isoformat(),
            }
        """
        return PidRegistration.get_registered(xml_with_pre)

    @classmethod
    def is_registered_xml_uri(cls, xml_uri):
        """
        Returns
        -------
            {"error": ""}
            or
            {
                "v3": self.v3,
                "v2": self.v2,
                "aop_pid": self.aop_pid,
                "xml_uri": self.xml_uri,
                "article": self.article,
                "created": self.created.isoformat(),
                "updated": self.updated.isoformat(),
            }
        """
        xml_with_pre = xml_sps_lib.get_xml_with_pre_from_uri(xml_uri)
        return cls.is_registered_xml_with_pre(xml_with_pre)

    @classmethod
    def is_registered_xml_zip(cls, zip_xml_file_path):
        """
        Returns
        -------
            list of dict
                {"error": ""}
                or
                {
                "v3": self.v3,
                "v2": self.v2,
                "aop_pid": self.aop_pid,
                "xml_uri": self.xml_uri,
                "article": self.article,
                "created": self.created.isoformat(),
                "updated": self.updated.isoformat(),
                }
        """
        for item in xml_sps_lib.get_xml_items(zip_xml_file_path):
            # {"filename": item: "xml": xml}
            registered = cls.is_registered_xml_with_pre(item["xml_with_pre"])
            item.update(registered or {})
            yield item

    @classmethod
    def get_xml_uri(cls, v3):
        """
        Retorna XML URI ou None
        """
        return PidRegistration.get_xml_uri(v3)

    def synchronize(self):
        """
        Identifica no pid provider local os registros que não
        estão sincronizados com o pid provider remoto (central) e
        faz a sincronização, registrando o XML local no pid provider remoto
        """
        if not self.pid_provider_api_post_xml:
            raise ValueError(
                _(
                    "Unable to synchronized data with central pid provider because API URI is missing"
                )
            )
        for item in PidRegistration.unsynchronized_items:
            try:
                name = item.pkg_name
                xml_with_pre = xml_sps_lib.get_xml_with_pre_from_uri(item.xml_uri)
                response = self.pid_provider_api.provide_pid(xml_with_pre, name)
                if response.get("xml_uri"):
                    item.set_synchronized(True)
            except Exception as e:
                item.failure = SyncFailure.create(
                    _("Unable to do remote pid registration {} {} {}").format(
                        name,
                        type(e),
                        e,
                    ),
                    e,
                    item.creator,
                )
                item.save()


class PidProviderAPI:
    """
    Interface com o pid provider
    """

    def __init__(
        self,
        pid_provider_api_post_xml,
        pid_provider_api_get_token,
        timeout,
        api_username,
        api_password,
    ):
        self.pid_provider_api_post_xml = pid_provider_api_post_xml
        self.pid_provider_api_get_token = pid_provider_api_get_token
        self.timeout = timeout
        self.api_username = api_username
        self.api_password = api_password

    def provide_pid(self, xml_with_pre, name):
        """
        name : str
            nome do arquivo xml
        """
        token = self._get_token(
            username=self.api_username,
            password=self.api_password,
            timeout=self.timeout,
        )
        logging.info(token)
        response = self._prepare_and_post_xml(xml_with_pre, name, token)
        if response:
            # atualiza xml_with_pre com valor do XML registrado no core
            xml_with_pre = xml_sps_lib.get_xml_with_pre_from_uri(response["xml_uri"])
        return response

    def _handle_response(self, response):
        return response.json()

    def _get_token(self, username, password, timeout):
        """
        curl -X POST 127.0.0.1:8000/api-token-auth/ \
            --data 'username=x&password=x'
        """
        try:
            response = requests.post(
                self.pid_provider_api_get_token,
                data={"username": username, "password": password},
                auth=HTTPBasicAuth(username, password),
                timeout=timeout,
            )
            resp = self._handle_response(response)
            return resp.get("access")
        except Exception as e:
            # TODO tratar as exceções
            raise exceptions.GetAPITokenError(
                _("Unable to get api token {} {} {} {}").format(
                    username,
                    password,
                    type(e),
                    e,
                )
            )

    def _prepare_and_post_xml(self, xml_with_pre, name, token):
        """
        name : str
            nome do arquivo xml
        """
        if self.pid_provider_api_post_xml:
            with TemporaryDirectory() as tmpdirname:
                name, ext = os.path.splitext(name)
                zip_xml_file_path = os.path.join(tmpdirname, name + ".zip")

                xml_sps_lib.create_xml_zip_file(
                    zip_xml_file_path, xml_with_pre.tostring()
                )

                response = self._post_xml(zip_xml_file_path, token, self.timeout)
                for item in response:
                    logging.info(item)
                    try:
                        return item["registered"]
                    except KeyError:
                        return item

    def _post_xml(self, zip_xml_file_path, token, timeout):
        """
        curl -X POST -S \
            -H "Content-Disposition: attachment;filename=arquivo.zip" \
            -F "file=@path/arquivo.zip;type=application/zip" \
            -H 'Authorization: Bearer eyJ0b2tlb' \
            http://localhost:8000/api/v2/pid/pid_provider/ --output output.json
        """
        try:
            basename = os.path.basename(zip_xml_file_path)

            files = {
                "file": (
                    basename,
                    open(zip_xml_file_path, "rb"),
                    "application/zip",
                )
            }
            header = {
                "Authorization": "Bearer " + token,
                "content-type": "multi-part/form-data",
                "Content-Disposition": "attachment; filename=%s" % basename,
            }
            response = requests.post(
                self.pid_provider_api_post_xml,
                files=files,
                headers=header,
                timeout=timeout,
                verify=False,
            )
            return self._handle_response(response)

        except Exception as e:
            logging.exception(e)
            raise exceptions.APIPidProviderPostError(
                _("Unable to get pid from pid provider {} {} {}").format(
                    zip_xml_file_path,
                    type(e),
                    e,
                )
            )


class PidRegistration:
    """
    Recebe XML para validar ou atribuir o ID do tipo v3
    """

    def __init__(self, files_storage_name):
        self.files_storage_manager = FilesStorageManager(files_storage_name)

    def unsynchronized_items(self):
        return PidRequesterXML.unsynchronized

    def register_pid(self, xml_with_pre, name, user, synchronized=None):
        """
        Fornece / Valida PID para o XML no formato de objeto de XMLWithPre

        Returns
        -------
            {
                "v3": self.v3,
                "v2": self.v2,
                "aop_pid": self.aop_pid,
                "xml_uri": self.xml_uri,
                "article": self.article,
                "created": self.created.isoformat(),
                "updated": self.updated.isoformat(),
                "xml_changed": boolean,
                "record_status": created | updated | retrieved
            }
            or
            {
                "error_type": self.error_type,
                "error_message": self.error_message,
                "id": self.finger_print,
                "basename": self.basename,
            }
        """
        return PidRequesterXML.register(
            xml_with_pre,
            name,
            user,
            self.push_xml_content,
            synchronized=synchronized,
        )

    @property
    def push_xml_content(self):
        return self.files_storage_manager.push_xml_content

    @classmethod
    def is_registered(cls, xml_with_pre):
        """
        Returns
        -------
            {"error": ""}
            or
            {
                "v3": self.v3,
                "v2": self.v2,
                "aop_pid": self.aop_pid,
                "xml_uri": self.xml_uri,
                "article": self.article,
                "created": self.created.isoformat(),
                "updated": self.updated.isoformat(),
            }
        """
        return PidRequesterXML.get_registered(xml_with_pre)

    @classmethod
    def get_xml_uri(cls, v3):
        """
        Retorna XML URI ou None
        """
        return PidRequesterXML.get_xml_uri(v3)
