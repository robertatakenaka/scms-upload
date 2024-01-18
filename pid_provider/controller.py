import logging
import sys

# from django.utils.translation import gettext as _
from packtools.sps.pid_provider.xml_sps_lib import XMLWithPre

from package.models import SPSPkg
from pid_provider.models import PidProviderXML
from pid_provider.client import PidProviderAPIClient
from tracker.models import UnexpectedEvent

LOGGER = logging.getLogger(__name__)
LOGGER_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


class BasePidProvider:

    def __init__(self):
        pass

    def provide_pid_for_xml_zip(
        self,
        zip_xml_file_path,
        user,
        filename=None,
        origin_date=None,
        force_update=None,
        is_published=None,
    ):
        """
        Fornece / Valida PID para o XML em um arquivo compactado

        Returns
        -------
            list of dict
        """
        try:
            for xml_with_pre in XMLWithPre.create(path=zip_xml_file_path):
                yield self.provide_pid_for_xml_with_pre(
                    xml_with_pre,
                    xml_with_pre.filename,
                    user,
                    origin_date=origin_date,
                    force_update=force_update,
                    is_published=is_published,
                    origin=zip_xml_file_path,
                )
        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            UnexpectedEvent.create(
                exception=e,
                exc_traceback=exc_traceback,
                detail={
                    "operation": "PidProvider.provide_pid_for_xml_zip",
                    "input": dict(
                        zip_xml_file_path=zip_xml_file_path,
                        user=user.username,
                        filename=filename,
                        origin_date=origin_date,
                        force_update=force_update,
                        is_published=is_published,
                    ),
                },
            )
            yield {
                "error_msg": f"Unable to provide pid for {zip_xml_file_path} {e}",
                "error_type": str(type(e)),
            }

    def provide_pid_for_xml_uri(
        self,
        xml_uri,
        name,
        user,
        origin_date=None,
        force_update=None,
        is_published=None,
    ):
        """
        Fornece / Valida PID de um XML disponível por um URI

        Returns
        -------
            dict
        """
        try:
            xml_with_pre = list(XMLWithPre.create(uri=xml_uri))[0]
        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            UnexpectedEvent.create(
                exception=e,
                exc_traceback=exc_traceback,
                detail={
                    "operation": "PidProvider.provide_pid_for_xml_uri",
                    "input": dict(
                        xml_uri=xml_uri,
                        user=user.username,
                        name=name,
                        origin_date=origin_date,
                        force_update=force_update,
                        is_published=is_published,
                    ),
                },
            )
            return {
                "error_msg": f"Unable to provide pid for {xml_uri} {e}",
                "error_type": str(type(e)),
            }
        else:
            return self.provide_pid_for_xml_with_pre(
                xml_with_pre,
                name,
                user,
                origin_date=origin_date,
                force_update=force_update,
                is_published=is_published,
                origin=xml_uri,
            )

    @classmethod
    def is_registered_xml_with_pre(cls, xml_with_pre, origin):
        """
        Returns
        -------
            {"error_type": "", "error_message": ""}
            or
            {
                "v3": self.v3,
                "v2": self.v2,
                "aop_pid": self.aop_pid,
                "xml_with_pre": self.xml_with_pre,
                "created": self.created.isoformat(),
                "updated": self.updated.isoformat(),
            }
        """
        return PidProviderXML.get_registered(xml_with_pre, origin)

    @classmethod
    def is_registered_xml_uri(cls, xml_uri):
        """
        Returns
        -------
            {"error_type": "", "error_message": ""}
            or
            {
                "v3": self.v3,
                "v2": self.v2,
                "aop_pid": self.aop_pid,
                "xml_with_pre": self.xml_with_pre,
                "created": self.created.isoformat(),
                "updated": self.updated.isoformat(),
            }
        """
        try:
            for xml_with_pre in XMLWithPre.create(uri=xml_uri):
                return cls.is_registered_xml_with_pre(xml_with_pre, xml_uri)
        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            UnexpectedEvent.create(
                exception=e,
                exc_traceback=exc_traceback,
                detail={
                    "operation": "PidProvider.is_registered_xml_uri",
                    "input": dict(
                        xml_uri=xml_uri,
                    ),
                },
            )
            return {
                "error_msg": f"Unable to check whether {xml_uri} is registered {e}",
                "error_type": str(type(e)),
            }

    @classmethod
    def is_registered_xml_zip(cls, zip_xml_file_path):
        """
        Returns
        -------
            list of dict
                {"error_type": "", "error_message": ""}
                or
                {
                "v3": self.v3,
                "v2": self.v2,
                "aop_pid": self.aop_pid,
                "xml_with_pre": self.xml_with_pre,
                "created": self.created.isoformat(),
                "updated": self.updated.isoformat(),
                }
        """
        try:
            for xml_with_pre in XMLWithPre.create(path=zip_xml_file_path):
                yield cls.is_registered_xml_with_pre(xml_with_pre, zip_xml_file_path)
        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            UnexpectedEvent.create(
                exception=e,
                exc_traceback=exc_traceback,
                detail={
                    "operation": "PidProvider.is_registered_xml_zip",
                    "input": dict(
                        zip_xml_file_path=zip_xml_file_path,
                    ),
                },
            )
            return {
                "error_msg": f"Unable to check whether {zip_xml_file_path} is registered {e}",
                "error_type": str(type(e)),
            }


class PidProvider(BasePidProvider):
    """
    Recebe XML para validar ou atribuir o ID do tipo v3
    """

    def __init__(self):
        self.pid_provider_api = PidProviderAPIClient()

    def provide_pid_for_xml_with_pre(
        self,
        xml_with_pre,
        name,
        user,
        origin_date=None,
        force_update=None,
        is_published=None,
        origin=None,
    ):
        """
        Recebe um xml_with_pre para solicitar o PID da versão 3
        """
        v3 = xml_with_pre.v3
        resp = self.pre_registration(xml_with_pre, name)

        if not resp["registered_in_upload"]:
            # não está registrado em Upload, realizar registro
            registered = PidProviderXML.register(
                xml_with_pre,
                name,
                user,
                origin_date=origin_date,
                force_update=force_update,
                is_published=is_published,
                origin=origin,
            )
            logging.info(f"PidProviderXML.register: {registered}")
            registered = registered or {}
            resp["registered_in_upload"] = bool(registered.get("v3"))
            resp.update(registered)

        resp["synchronized"] = resp["registered_in_core"] and resp["registered_in_upload"]
        resp["xml_with_pre"] = xml_with_pre
        resp["filename"] = name
        logging.info(f"PidProvider.provide_pid_for_xml_with_pre: resp={resp}")
        return resp

    def pre_registration(self, xml_with_pre, name):
        """
        Verifica a necessidade de registro no Upload e/ou Core
        Se aplicável, faz registro no Core
        Se aplicável, informa necessidade de registro no Upload

        Returns
        -------
        {'filename': '1518-8787-rsp-38-suppl-65.xml',
        'origin': '/app/core/media/1518-8787-rsp-38-suppl-65_wScfJap.zip',
        'v3': 'Lfh9K7RWn4Wt9XFfx3dY8vj',
        'v2': 'S0034-89102004000700010',
        'aop_pid': None,
        'pkg_name': '1518-8787-rsp-38-suppl-65',
        'created': '2024-01-16T19:35:21.454225+00:00',
        'updated': '2024-01-18T21:33:11.805681+00:00',
        'record_status': 'updated',
        'xml_changed': False}

        ou

        {"error_type": "ERROR ..."}

        """
        # retorna os dados se está registrado e é igual a xml_with_pre
        registered = PidProviderXML.is_registered(xml_with_pre)

        if registered.get("error_type"):
            return registered

        registered = registered or {}

        pid_v3 = registered.get("v3")

        registered["registered_in_upload"] = bool(pid_v3)
        registered["registered_in_core"] = SPSPkg.is_registered_in_core(pid_v3)

        if not registered["registered_in_core"]:
            # registra em Core
            response = self.pid_provider_api.provide_pid(xml_with_pre, name)
            if response.get("v3"):
                # está registrado em core
                registered["registered_in_core"] = True
                registered.update(response)

        logging.info(f"PidProvider.pre_registration: response: {registered}")
        return registered
