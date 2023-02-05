from .. import models
from files_storage.models import XMLFile
from xmlsps.models import XMLDocPid


def run():
    models.MigratedDocument.objects.all().delete()
    XMLDocPid.objects.all().delete()
    XMLFile.objects.all().delete()
