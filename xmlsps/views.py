from zipfile import ZipFile
import shutil
import os
import logging
from tempfile import TemporaryDirectory

from django.db.models import Q
from django.core.files import File
from django.core.files.storage import FileSystemStorage
from rest_framework.exceptions import ParseError
from rest_framework.parsers import FileUploadParser
from rest_framework.authentication import (
    SessionAuthentication, BasicAuthentication,
    TokenAuthentication,
)
from django.contrib.auth import authenticate, login
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.mixins import (
    CreateModelMixin, ListModelMixin, RetrieveModelMixin, UpdateModelMixin
)
from rest_framework.viewsets import GenericViewSet

from . import models
from . import serializers
from . import controller
from . import exceptions


class XMLViewSet(
        GenericViewSet,  # generic view functionality
        CreateModelMixin,  # handles POSTs
        RetrieveModelMixin,  # handles GETs for 1 Company
        ListModelMixin):  # handles GETs for many Companies

    http_method_names = ['get', 'head']
    # authentication_classes = [SessionAuthentication, BasicAuthentication]
    # authentication_classes = [BasicAuthentication]
    # permission_classes = [IsAuthenticated]

    serializer_class = serializers.XMLArticleSerializer
    queryset = models.EncodedXMLArticle.objects.all()

    def list(self, request, pk=None):
        from_date = request.query_params.get('from_date')
        issn = request.query_params.get('issn')
        pub_year = request.query_params.get('pub_year')

        qs = []
        params = {}
        if from_date:
            params['updated__gte'] = from_date
        if issn:
            qs.append(
                (Q(journal__issn_electronic=issn) |
                    Q(journal__issn_print=issn))
            )
        if pub_year:
            next_year = str(int(pub_year)+1)
            qs.append(
                Q(issue__pub_year=issn) |
                (Q(article_publication_date__gte=pub_year) &
                    Q(article_publication_date__lt=next_year))
            )
        q = None
        for item in qs:
            if q:
                q &= item
            else:
                q = item

        if q:
            queryset = models.EncodedXMLArticle.objects.filter(q, **params).iterator()
        elif params:
            queryset = models.EncodedXMLArticle.objects.filter(**params).iterator()
        else:
            queryset = models.EncodedXMLArticle.objects.iterator()
        serializer = serializers.XMLArticleSerializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        v3 = pk
        xml_uri = models.EncodedXMLArticle.get_xml_uri(v3=v3)
        if xml_uri:
            content = {'v3': v3, "xml_uri": xml_uri}
            return Response(content, status=status.HTTP_200_OK)
        else:
            content = {'v3': v3, 'error': 'not found'}
            return Response(content, status=status.HTTP_400_BAD_REQUEST)


class PidProviderViewSet(
        GenericViewSet,  # generic view functionality
        CreateModelMixin,  # handles POSTs
        RetrieveModelMixin,  # handles GETs for 1 Company
        ListModelMixin):  # handles GETs for many Companies

    parser_classes = (FileUploadParser, )
    http_method_names = ['post', 'get', 'head']

    authentication_classes = [
        # SessionAuthentication,
        BasicAuthentication,
        # TokenAuthentication,
    ]
    # permission_classes = [IsAuthenticated]

    serializer_class = serializers.XMLArticleSerializer
    queryset = models.EncodedXMLArticle.objects.all()

    @property
    def pid_provider(self):
        if not hasattr(self, '_pid_provider') or not self._pid_provider:
            self._pid_provider = controller.PidProvider('pid-provider')
        return self._pid_provider

    def _authenticate(self, request):
        try:
            username = request.data['username']
            password = request.data['password']
        except:
            pass
        try:
            logging.info(request.headers)
        except:
            pass

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)

    def list(self, request, pk=None):
        """
        List items filtered by from_date, issn, pub_year

        Return
        ------
            list of dict
        """
        from_date = request.query_params.get('from_date')
        issn = request.query_params.get('issn')
        pub_year = request.query_params.get('pub_year')

        qs = []
        params = {}
        if from_date:
            params['updated__gte'] = from_date
        if issn:
            qs.append(
                (Q(journal__issn_electronic=issn) |
                    Q(journal__issn_print=issn))
            )
        if pub_year:
            next_year = str(int(pub_year)+1)
            qs.append(
                Q(issue__pub_year=issn) |
                (Q(article_publication_date__gte=pub_year) &
                    Q(article_publication_date__lt=next_year))
            )
        q = None
        for item in qs:
            if q:
                q &= item
            else:
                q = item

        if q:
            queryset = models.EncodedXMLArticle.objects.filter(q, **params).iterator()
        elif params:
            queryset = models.EncodedXMLArticle.objects.filter(**params).iterator()
        else:
            queryset = models.EncodedXMLArticle.objects.iterator()
        serializer = serializers.XMLArticleSerializer(queryset, many=True)
        return Response(serializer.data)

    def create(self, request, format='zip'):
        """
        Receive a zip file which contains XML file(s)
        Register / Update XML data and files

        Return
        ------
            list of dict (filename, xml_changed, registered or error)
        """
        try:
            self._authenticate(request)
            logging.info(request.data)
            logging.info(request.FILES)
            if 'file' not in request.data:
                raise ParseError("Empty content")

            uploaded_file = request.FILES["file"]
            logging.info(uploaded_file.name)

            fs = FileSystemStorage()
            downloaded_file = fs.save(uploaded_file.name, uploaded_file)
            downloaded_file_path = fs.path(downloaded_file)

            results = self.pid_provider.provide_pids_for_xml_zip(
                zip_xml_file_path=downloaded_file_path,
                user=request.user,
            )
            results = list(results)
            for item in results:
                if item.get("error"):
                    return Response(
                        list(results),
                        status=status.HTTP_400_BAD_REQUEST)
            return Response(results, status=status.HTTP_201_CREATED)
        except Exception as e:
            logging.exception(e)
            return Response(
                [{"error": str(e), "type_error": str(type(e))}],
                status=status.HTTP_400_BAD_REQUEST)

    # def retrieve(self, request, pk=None):
    #     try:
    #         user = request.user
    #         logging.info(user)
    #         logging.info(request.data)
    #         logging.info(request.FILES)
    #         if 'file' not in request.data:
    #             raise ParseError("Empty content")

    #         uploaded_file = request.FILES["file"]
    #         logging.info(uploaded_file.name)

    #         fs = FileSystemStorage()
    #         downloaded_file = fs.save(uploaded_file.name, uploaded_file)
    #         downloaded_file_path = fs.path(downloaded_file)

    #         results = self.pid_provider.get_registered_for_xml_zip(
    #             zip_xml_file_path=downloaded_file_path,
    #         )
    #         return Response(results, status=status.HTTP_200_OK)
    #     except Exception as e:
    #         return Response(
    #             [{"error": str(e), "type_error": str(type(e))}],
    #             status=status.HTTP_400_BAD_REQUEST)


class PidRequesterViewSet(
        GenericViewSet,  # generic view functionality
        RetrieveModelMixin,  # handles GETs for 1 Company
        ListModelMixin):  # handles GETs for many Companies

    http_method_names = ['get', 'head']

    authentication_classes = [
        # SessionAuthentication,
        BasicAuthentication,
        # TokenAuthentication,
    ]
    # permission_classes = [IsAuthenticated]

    serializer_class = serializers.XMLArticleSerializer
    queryset = models.EncodedXMLArticle.objects.all()

    def list(self, request, pk=None):
        """
        List the records which synchronized = false
        """
        queryset = models.EncodedXMLArticle.objects.filter(synchronized=False)
        serializer = serializers.XMLArticleSerializer(queryset, many=True)
        return Response(serializer.data)

    # def retrieve(self, request, pk=None):
    #     v3 = pk
    #     xml_uri = models.EncodedXMLArticle.get_xml_uri(v3=v3)
    #     if xml_uri:
    #         content = {'v3': v3, "xml_uri": xml_uri}
    #         return Response(content, status=status.HTTP_200_OK)
    #     else:
    #         content = {'v3': v3, 'error': 'not found'}
    #         return Response(content, status=status.HTTP_400_BAD_REQUEST)
