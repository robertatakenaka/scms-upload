import logging

from django.db.models import Q
from rest_framework.parsers import FileUploadParser
from rest_framework.authentication import SessionAuthentication, BasicAuthentication
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
    # authentication_classes = [SessionAuthentication, BasicAuthentication]
    # authentication_classes = [BasicAuthentication]
    # permission_classes = [IsAuthenticated]

    serializer_class = serializers.XMLArticleSerializer
    queryset = models.EncodedXMLArticle.objects.all()

    @property
    def pid_provider(self):
        if not hasattr(self, '_pid_provider') or not self._pid_provider:
            self._pid_provider = controller.PidProvider('pid-provider')
        return self._pid_provider

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

    def create(self, request):
        logging.info("create..............")
        logging.info(request.data.getlist('zip_xml_file_path'))
        user = request.user
        logging.info(user)
        # zip_xml_file_path = request.FILES.get('zip_xml_file_path')
        # logging.info(zip_xml_file_path)
        # results = self.pid_provider.request_document_ids_for_xml_zip(
        #     zip_xml_file_path=zip_xml_file_path,
        #     user=user,
        # )
        return Response({}, status=status.HTTP_201_CREATED)
        # try:
        #     logging.info(request.FILES)
        #     user = request.user
        #     logging.info(user)
        #     zip_xml_file_path = request.FILES['zip_xml_file_path']
        #     results = self.pid_provider.request_document_ids_for_xml_zip(
        #         zip_xml_file_path=zip_xml_file_path,
        #         user=user,
        #     )

        #     items = []
        #     errors = []
        #     for result in results:
        #         registered = result and result.get("registered")
        #         if registered:
        #             items.append({
        #                 "filename": result['filename'],
        #                 "v3": registered.v3,
        #                 "xml_uri": registered.xml_uri,
        #             })
        #         else:
        #             errors.append(result)
        #     if items and errors:
        #         return Response(items + errors, status=status.HTTP_201_CREATED)
        #     elif items:
        #         return Response(items, status=status.HTTP_201_CREATED)
        #     else:
        #         return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        # except Exception as e:
        #     return Response(
        #         [{"error": str(e), "type_error": str(type(e))}],
        #         status=status.HTTP_400_BAD_REQUEST)

    def retrieve(self, request, pk=None):
        try:
            user = request.user
            logging.info(user)
            zip_xml_file_path = request.FILES['zip_xml_file_path']
            results = self.pid_provider.get_registered_xml_zip(
                zip_xml_file_path=zip_xml_file_path,
            )

            items = []
            errors = []
            for result in results:
                registered = result and result.get("registered")
                if registered:
                    items.append({
                        "filename": result['filename'],
                        "v3": registered.v3,
                        "xml_uri": registered.xml_uri,
                    })
                else:
                    errors.append(result)
            if items and errors:
                return Response(items + errors, status=status.HTTP_201_CREATED)
            elif items:
                return Response(items, status=status.HTTP_201_CREATED)
            else:
                return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                [{"error": str(e), "type_error": str(type(e))}],
                status=status.HTTP_400_BAD_REQUEST)


class PidRequesterViewSet(
        GenericViewSet,  # generic view functionality
        RetrieveModelMixin,  # handles GETs for 1 Company
        ListModelMixin):  # handles GETs for many Companies

    http_method_names = ['get', 'head']
    # authentication_classes = [SessionAuthentication, BasicAuthentication]
    authentication_classes = [BasicAuthentication]
    permission_classes = [IsAuthenticated]

    serializer_class = serializers.XMLArticleSerializer
    queryset = models.EncodedXMLArticle.objects.all()

    def list(self, request, pk=None):
        queryset = models.EncodedXMLArticle.objects.filter(synchronized=False)
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
