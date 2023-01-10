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


class PidV3ViewSet(GenericViewSet,  # generic view functionality
                   CreateModelMixin,  # handles POSTs
                   RetrieveModelMixin,  # handles GETs for 1 Company
                   UpdateModelMixin,  # handles PUTs and PATCHes
                   ListModelMixin):  # handles GETs for many Companies

    serializer_class = serializers.PidV3Serializer
    queryset = models.PidV3.objects.all()

    """
    Example empty viewset demonstrating the standard
    actions that will be handled by a router class.

    If you're using format suffixes, make sure to also include
    the `format=None` keyword argument for each action.
    """

    def list(self, request, pk=None):
        queryset = models.PidV3.objects.filter(synchronized=False)
        content = {'message': 'list'}
        return Response(content)

    def create(self, request):
        try:
            user = request.user
            zip_xml_file_path = request.FILES['zip_xml_file_path']
            provider = controller.PidProvider('pid-provider')
            results = provider.request_document_ids_for_xml_zip(
                zip_xml_file_path=zip_xml_file_path,
                user=user)

            items = []
            errors = []
            for result in results:
                registered = result.get("registered")
                if registered:
                    items.append({
                        "filename": result['filename'],
                        "v3": registered.v3,
                        "xml_uri": registered.xml_uri,
                    })
                else:
                    errors.append(Response)
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

    def retrieve(self, request, pk=None):
        content = {
            'message':
            'Hello, %s!' % (pk or self.request.data.get("v3") or '')
        }
        return Response(content)

    # def retrieve(self, request, pk=None):
    #     v3 = request.data['v3']
    #     xml_uri = controller.get_xml_uri(v3=v3)
    #     if xml_uri:
    #         content = {'v3': v3, "xml_uri": xml_uri}
    #         return Response(content, status=status.HTTP_200_OK)
    #     else:
    #         content = {'v3': v3, 'error': 'not found'}
    #         return Response(content, status=status.HTTP_404_NOT_FOUND)

    # def update(self, request, pk=None):
    #     pass

    # def partial_update(self, request, pk=None):
    #     pass

    # def destroy(self, request, pk=None):
    #     pass
