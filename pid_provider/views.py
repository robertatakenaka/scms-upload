import logging

from django.db.models import Q
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

from xmlsps import models
from pid_provider.serializer import XMLArticleSerializer
from pid_provider import controller


class ArticleXMLViewSet(
        GenericViewSet,  # generic view functionality
        CreateModelMixin,  # handles POSTs
        RetrieveModelMixin,  # handles GETs for 1 Company
        ListModelMixin):  # handles GETs for many Companies

    http_method_names = ['get', 'head']
    # authentication_classes = [SessionAuthentication, BasicAuthentication]
    # authentication_classes = [BasicAuthentication]
    # permission_classes = [IsAuthenticated]

    serializer_class = XMLArticleSerializer
    queryset = models.XMLDocPid.objects.all()

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
            queryset = models.XMLDocPid.objects.filter(q, **params).iterator()
        elif params:
            queryset = models.XMLDocPid.objects.filter(**params).iterator()
        else:
            queryset = models.XMLDocPid.objects.iterator()
        serializer = XMLArticleSerializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        v3 = pk
        xml_uri = models.XMLDocPid.get_xml_uri(v3=v3)
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

    serializer_class = XMLArticleSerializer
    queryset = models.XMLDocPid.objects.all()

    @property
    def pid_provider(self):
        if not hasattr(self, '_pid_provider') or not self._pid_provider:
            self._pid_provider = controller.PidProvider('pid-provider')
        return self._pid_provider

    def _authenticate(self, request):
        logging.info("_authenticate %s" % request.data)
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
            queryset = models.XMLDocPid.objects.filter(q, **params).iterator()
        elif params:
            queryset = models.XMLDocPid.objects.filter(**params).iterator()
        else:
            queryset = models.XMLDocPid.objects.iterator()
        serializer = XMLArticleSerializer(queryset, many=True)
        return Response(serializer.data)

    def create(self, request, format='zip'):
        """
        Receive a zip file which contains XML file(s)
        Register / Update XML data and files

        curl -X POST -S \
            -H "Content-Disposition: attachment;filename=pacote_xml.zip" \
            -F "file=@/path/pacote_xml.zip;type=application/zip" \
            --user "adm:adm" \
            127.0.0.1:8000/pid_provider/

        Return
        ------
            list of dict (filename, xml_changed, registered or error)
        """
        try:
            # self._authenticate(request)
            logging.info("Receiving files %s" % request.FILES)
            logging.info("Receiving data %s" % request.data)
            # if 'file' not in request.data:
            #     raise ParseError("Empty content")

            uploaded_file = request.FILES["file"]
            logging.info("Receiving file name %s" % uploaded_file.name)

            fs = FileSystemStorage()
            downloaded_file = fs.save(uploaded_file.name, uploaded_file)
            downloaded_file_path = fs.path(downloaded_file)

            logging.info("Receiving temp %s" % downloaded_file_path)
            results = self.pid_provider.register_xml_zip(
                zip_xml_file_path=downloaded_file_path,
                user=request.user,
            )
            results = list(results)
            for item in results:
                if item.get("error"):
                    return Response(results,
                                    status=status.HTTP_400_BAD_REQUEST)
            return Response(results, status=status.HTTP_201_CREATED)
        except Exception as e:
            logging.exception(e)
            return Response(
                [{"request data": request.data,
                  "error": str(e), "type_error": str(type(e))}],
                status=status.HTTP_400_BAD_REQUEST)
