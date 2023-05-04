from unittest.mock import patch, Mock, MagicMock

from lxml import etree
from django.contrib.auth import get_user_model
from django.test import TestCase

from pid_requester.controller import PidRequester
from pid_requester.models import PidProviderConfig


User = get_user_model()


# def get_mock_config():
#     config = object()
#     config.host = ''
#     config.access_key = ''
#     config.secret_key = ''
#     config.bucket_root = ''
#     config.bucket_app_subdir = 'bucket-app-subdir'
#     config.secure = ''
#     return config


@patch("pid_requester.controller.xml_sps_lib.get_xml_with_pre_from_uri")
@patch("pid_requester.controller.requests.post")
@patch("pid_requester.models.PidRequesterXML.register")
@patch("pid_requester.controller.PidProviderConfig.get_or_create")
class PidRequesterTest(TestCase):
    def test_request_pid_for_xml_zip(
        self, mock_pid_provider_config,
        mock_models_register, mock_post, mock_get_xml_with_pre_from_uri
    ):
        data = {
            "v3": "V3",
            "v2": "V2",
            "aop_pid": "AOPPID",
            "xml_uri": "URI",
            "article": "ARTICLE",
            "created": "2020-01-02T00:00:00",
            "updated": "2020-01-02T00:00:00",
            "record_status": "created",
            "xml_changed": True,
        }
        # dubla a configuração de pid provider
        mock_pid_provider_config.return_value = MagicMock(PidProviderConfig)
        # dubla a função que retorna a árvore de XML a partir de um URI
        mock_get_xml_with_pre_from_uri.return_value = etree.fromstring("<root/>")

        # dubla resposta da requisição do token
        mock_get_token_response = Mock()
        mock_get_token_response.json = Mock()
        mock_get_token_response.json.return_value = {
            "refresh": "eyJhbGciO...",
            "access": "eyJ0b2tlb...",
        }
        # dubla resposta da requisição do PID v3
        mock_post_xml_response = Mock()
        mock_post_xml_response.json = Mock()
        mock_post_xml_response.json.return_value = [data]

        mock_post.side_effect = [
            mock_get_token_response,
            mock_post_xml_response,
        ]
        mock_models_register.return_value = data

        pid_requester = PidRequester()
        result = pid_requester.request_pid_for_xml_zip(
            zip_xml_file_path="./pid_requester/fixtures/sub-article/2236-8906-hoehnea-49-e1082020.xml.zip",
            user=User.objects.first(),
            synchronized=None,
        )
        result = list(result)
        self.assertEqual("V3", result[0]["v3"])
        self.assertEqual("V2", result[0]["v2"])
        self.assertEqual("AOPPID", result[0]["aop_pid"])
        self.assertEqual("URI", result[0]["xml_uri"])
        self.assertEqual("ARTICLE", result[0]["article"])
        self.assertEqual("2020-01-02T00:00:00", result[0]["created"])
        self.assertEqual("2020-01-02T00:00:00", result[0]["updated"])
        self.assertEqual("2236-8906-hoehnea-49-e1082020.xml", result[0]["filename"])
        self.assertEqual("created", result[0]["record_status"])
        self.assertEqual(True, result[0]["xml_changed"])
