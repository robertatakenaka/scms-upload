import json
import logging
import sys
import traceback
import urllib

from django.utils.translation import gettext_lazy as _
from requests import HTTPError
from requests.auth import HTTPBasicAuth

from core.utils.requester import post_data
from publication.api import exceptions


class PublicationAPI:
    """
    Interface com o site
    """

    def __init__(
        self,
        post_data_url=None,
        get_token_url=None,
        username=None,
        password=None,
        timeout=None,
        token=None,
    ):
        self.timeout = timeout or 15
        self.post_data_url = post_data_url
        self.get_token_url = get_token_url
        self.username = username
        self.password = password
        self.token = token

    @property
    def data(self):
        return dict(
            post_data_url=self.post_data_url,
            get_token_url=self.get_token_url,
            username=self.username,
            password=self.password,
        )

    def post_data(self, payload, kwargs=None):
        """
        payload : dict
        """
        # logging.info(f"payload={payload}")
        response = None
        try:
            try:
                self.token = self.token or self.get_token()
                response = self._post_data(payload, self.token, kwargs)
            except Exception as e:
                self.token = self.get_token()
                response = self._post_data(payload, self.token, kwargs)
        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            response = {
                "post_data_url": self.post_data_url,
                "payload": payload,
                "traceback": traceback.format_tb(exc_traceback),
                "error": str(e),
                "error_type": str(type(e)),
            }
            return response

        if response.get("id") and response["id"] != "None":
            response["result"] = "OK"
        elif response.get("failed") is False:
            response["result"] = "OK"
        return response or {}

    def get_token(self):
        """
        curl -X POST 127.0.0.1:8000/api/v1/auth \
            --data 'username=x&password=x'
        """
        if not self.get_token_url:
            return

        resp = post_data(
            self.get_token_url,
            # data={"username": self.username, "password": self.password},
            auth=(self.username, self.password),
            timeout=self.timeout,
            json=True,
        )
        # logging.info(resp)
        return resp.get("token")

    def _post_data(self, payload, token, kwargs=None):
        """
        payload : dict
        token : str

        curl -X POST -S \
            -H 'Authorization: Basic eyJ0b2tlb' \
            http://localhost:8000/api/v1/journal/
        """
        if token:
            header = {
                "Authorization": "Basic " + token,
                "Content-Type": "application/json",
            }
        else:
            header = {}

        # logging.info(self.post_data_url)
        if kwargs:
            params = "&" + urllib.parse.urlencode(kwargs)
        else:
            params = ""
        return post_data(
            f"{self.post_data_url}/?token={token}{params}",
            data=json.dumps(payload),
            headers=header,
            timeout=self.timeout,
            verify=False,
            json=True,
        )
