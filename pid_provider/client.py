import logging
import os
import sys
from tempfile import TemporaryDirectory

from django.utils.translation import gettext as _
from packtools.sps.pid_provider.xml_sps_lib import (
    XMLWithPre,
    create_xml_zip_file,
    get_xml_with_pre,
)
from provides.auth import HTTPBasicAuth

from pid_provider import exceptions
from pid_provider.models import PidProviderConfig
from pid_provider.utils.provideer import post_data


LOGGER = logging.getLogger(__name__)
LOGGER_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


class PidProviderAPI:
    """
    Interface com o pid provider
    """

    def __init__(
        self,
        pid_provider_api_post_xml=None,
        pid_provider_api_get_token=None,
        timeout=None,
        api_username=None,
        api_password=None,
    ):
        self.timeout = timeout or 15
        self._pid_provider_api_post_xml = pid_provider_api_post_xml
        self._pid_provider_api_get_token = pid_provider_api_get_token
        self._api_username = api_username
        self._api_password = api_password

    @property
    def config(self):
        if not hasattr(self, "_config") or not self._config:
            try:
                self._config = PidProviderConfig.get_or_create()
            except Exception as e:
                logging.exception(f"PidProviderConfig.get_or_create {e}")
                self._config = None
        return self._config

    @property
    def pid_provider_api_post_xml(self):
        if self._pid_provider_api_post_xml is None:
            try:
                self._pid_provider_api_post_xml = self.config.pid_provider_api_post_xml
            except AttributeError as e:
                raise exceptions.APIPidProviderConfigError(e)
        return self._pid_provider_api_post_xml

    @property
    def pid_provider_api_get_token(self):
        if self._pid_provider_api_get_token is None:
            try:
                self._pid_provider_api_get_token = (
                    self.config.pid_provider_api_get_token
                )
            except AttributeError as e:
                raise exceptions.APIPidProviderConfigError(e)
        return self._pid_provider_api_get_token

    @property
    def api_username(self):
        if self._api_username is None:
            try:
                self._api_username = self.config.api_username
            except AttributeError as e:
                raise exceptions.APIPidProviderConfigError(e)
        return self._api_username

    @property
    def api_password(self):
        if self._api_password is None:
            try:
                self._api_password = self.config.api_password
            except AttributeError as e:
                raise exceptions.APIPidProviderConfigError(e)
        return self._api_password

    def provide_pid(self, xml_with_pre, name):
        """
        name : str
            nome do arquivo xml
        """
        try:
            token = self._get_token(
                username=self.api_username,
                password=self.api_password,
                timeout=self.timeout,
            )
            response = self._prepare_and_post_xml(xml_with_pre, name, token)

            self._process_post_xml_response(response, xml_with_pre)
            try:
                return response[0]
            except IndexError:
                return
        except (
            exceptions.GetAPITokenError,
            exceptions.APIPidProviderPostError,
            exceptions.APIPidProviderConfigError,
        ) as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            return {
                "error_msg": str(e),
                "error_type": str(type(e)),
                "traceback": [
                    str(item) for item in traceback.extract_tb(exc_traceback)
                ],
            }

    def _get_token(self, username, password, timeout):
        """
        curl -X POST 127.0.0.1:8000/api-token-auth/ \
            --data 'username=x&password=x'
        """
        try:
            logging.info(self.pid_provider_api_get_token)
            resp = post_data(
                self.pid_provider_api_get_token,
                data={"username": username, "password": password},
                auth=HTTPBasicAuth(username, password),
                timeout=timeout,
                json=True,
            )
            logging.info(resp)
            return resp.get("access")
        except Exception as e:
            # TODO tratar as exceções
            logging.exception(e)
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
        with TemporaryDirectory() as tmpdirname:
            name, ext = os.path.splitext(name)
            zip_xml_file_path = os.path.join(tmpdirname, name + ".zip")

            create_xml_zip_file(zip_xml_file_path, xml_with_pre.tostring())

            return self._post_xml(zip_xml_file_path, token, self.timeout)

    def _post_xml(self, zip_xml_file_path, token, timeout):
        """
        curl -X POST -S \
            -H "Content-Disposition: attachment;filename=arquivo.zip" \
            -F "file=@path/arquivo.zip;type=application/zip" \
            -H 'Authorization: Bearer eyJ0b2tlb' \
            http://localhost:8000/api/v2/pid/pid_provider/ --output output.json
        """
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
        try:
            logging.info(self.pid_provider_api_post_xml)
            return post_data(
                self.pid_provider_api_post_xml,
                files=files,
                headers=header,
                timeout=timeout,
                verify=False,
                json=True,
            )
        except Exception as e:
            logging.exception(e)
            raise exceptions.APIPidProviderPostError(
                _("Unable to get pid from pid provider {} {} {}").format(
                    zip_xml_file_path,
                    type(e),
                    e,
                )
            )

    def _process_post_xml_response(self, response, xml_with_pre):
        logging.info(f"_process_post_xml_response: {response}")
        if not response:
            return
        for item in response:
            if not item.get("xml_changed"):
                return
            try:
                xml_with_pre = get_xml_with_pre(item["xml"])
            except KeyError:
                pass
            try:
                # atualiza xml_with_pre com valor do XML registrado no core
                for xml_with_pre in XMLWithPre.create(uri=item["xml_uri"]):
                    break
            except KeyError:
                pass
