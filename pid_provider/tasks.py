import logging
import json

from django.contrib.auth import get_user_model
from django.utils.translation import gettext as _

from config import celery_app
from publication.documents import get_document
from publication.db import mk_connection, disconnect
from pid_provider.controller import ArticleXMLRegistration


User = get_user_model()


@celery_app.task(bind=True, name=_("Request PID for documents registered in the new website"))
def migrate_kernel_xmls(
        self, pids_file_path, db_uri, user_id, files_storage_app_name):
    creator = User.objects.get(pk=user_id)
    documents = _get_new_website_xmls(pids_file_path, db_uri)

    output_file = pids_file_path + ".requests.out"
    with open(output_file, "w") as fp:
        fp.write("")

    for doc in documents:
        try:
            ArticleXMLRegistration().register_xml_uri(
                doc['xml'], doc['v3'] + ".xml",
                creator,
            )
        except KeyError:
            pass
        except Exception as e:
            logging.exception(
                f"Unable to register id for {doc} {type(e)} {e}"
            )
            with open(output_file, "a") as fp:
                fp.write(
                    json.dumps({"xml": doc['xml'], "v3": doc['v3']}) + "\n")


def _get_new_website_xmls(pids_file_path, db_uri):

    try:
        disconnect()
    except:
        pass
    mk_connection(host=db_uri, alias=None)

    output_file = pids_file_path + ".pids.out"
    with open(output_file, "w") as fp:
        fp.write("")

    with open(pids_file_path) as fp:
        for pid in sorted(fp.readlines()):
            pid = pid.strip()
            try:
                document = get_document(pid=pid)
                if not document._id:
                    document = get_document(aop_pid=pid)
                yield {"xml": document.xml, "v3": document._id}
            except Exception as e:
                logging.exception(
                    f"Unable to get document which pid is {pid}"
                )
                with open(output_file, "a") as fp:
                    fp.write(f"{pid}\n")
