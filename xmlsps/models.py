from datetime import datetime
from http import HTTPStatus
from shutil import copyfile
import hashlib
import logging

from django.db import models
from django.utils.translation import gettext as _
from wagtail.admin.edit_handlers import FieldPanel

from core.models import CommonControlField
from files_storage.controller import FilesStorageManager
from files_storage.models import MinioFile, FileWithLang, XMLFile
from files_storage.exceptions import PushPidProviderXMLError
from .xml_sps_lib import get_xml_with_pre_from_uri
from . import xml_sps_adapter
from . import exceptions
from . import v3_gen


LOGGER = logging.getLogger(__name__)
LOGGER_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def utcnow():
    return datetime.utcnow()
    # return datetime.utcnow().isoformat().replace("T", " ") + "Z"


class XMLJournal(models.Model):
    """
    <journal-meta>
      <journal-id journal-id-type="nlm-ta">J Bras Pneumol</journal-id>
      <journal-id journal-id-type="publisher-id">jbpneu</journal-id>
      <journal-title-group>
        <journal-title>Jornal Brasileiro de Pneumologia</journal-title>
        <abbrev-journal-title abbrev-type="publisher">J. bras. pneumol.</abbrev-journal-title>
      </journal-title-group>
      <issn pub-type="epub">1806-3756</issn>
      <publisher>
        <publisher-name>Sociedade Brasileira de Pneumologia e Tisiologia</publisher-name>
      </publisher>
    </journal-meta>
    """
    title = models.CharField(_("title"), max_length=256, null=True, blank=True)
    issn_electronic = models.CharField(_("issn_epub"), max_length=9, null=True, blank=True)
    issn_print = models.CharField(_("issn_ppub"), max_length=9, null=True, blank=True)

    class Meta:
        unique_together = [
            ['issn_electronic', 'issn_print'],
        ]
        indexes = [
            models.Index(fields=['issn_electronic']),
            models.Index(fields=['issn_print']),
        ]

    def __str__(self):
        return f'{self.issn_electronic} {self.issn_print}'

    @property
    def data(self):
        return dict(
            title=self.title,
            issn_electronic=self.issn_electronic,
            issn_print=self.issn_print,
        )

    @classmethod
    def get_or_create(cls, issn_electronic, issn_print):
        try:
            params = {
                "issn_electronic": issn_electronic,
                "issn_print": issn_print,
            }
            kwargs = _set_isnull_parameters(params)
            LOGGER.info("Search {}".format(kwargs))
            return cls.objects.get(**kwargs)
        except cls.DoesNotExist:
            params = {k: v for k, v in params.items() if v}
            LOGGER.info("Create {}".format(params))
            journal = cls(**params)
            journal.save()
            return journal


class XMLIssue(models.Model):
    journal = models.ForeignKey('XMLJournal', on_delete=models.SET_NULL, null=True, blank=True)
    pub_year = models.IntegerField(_("pub_year"), null=False)
    volume = models.CharField(_("volume"), max_length=10, null=True, blank=True)
    number = models.CharField(_("number"), max_length=10, null=True, blank=True)
    suppl = models.CharField(_("suppl"), max_length=10, null=True, blank=True)

    class Meta:
        unique_together = [
            ['journal', 'pub_year', 'volume', 'number', 'suppl'],
        ]
        indexes = [
            models.Index(fields=['journal']),
            models.Index(fields=['volume']),
            models.Index(fields=['number']),
            models.Index(fields=['suppl']),
            models.Index(fields=['pub_year']),
        ]

    def __str__(self):
        return f'{self.journal} {self.volume or ""} {self.number or ""} {self.suppl or ""}'

    @property
    def data(self):
        return dict(
            journal=self.journal.data,
            pub_year=self.pub_year,
            volume=self.volume,
            number=self.number,
            suppl=self.suppl,
        )

    @classmethod
    def get_or_create(cls, journal, volume, number, suppl, pub_year):
        try:
            params = {
                "volume": volume,
                "number": number,
                "suppl": suppl,
                "journal": journal,
                "pub_year": pub_year and int(pub_year) or None,
            }
            kwargs = _set_isnull_parameters(params)
            LOGGER.info("Search {}".format(kwargs))
            return cls.objects.get(**kwargs)
        except cls.DoesNotExist:
            params = {k: v for k, v in params.items() if v}
            LOGGER.info("Create {}".format(params))
            issue = cls(**params)
            issue.save()
            return issue


class SyncFailure(CommonControlField):
    message = models.CharField(
        _('Message'), max_length=255, null=True, blank=True)
    exception_type = models.CharField(
        _('Exception Type'), max_length=255, null=True, blank=True)
    exception_msg = models.CharField(
        _('Exception Msg'), max_length=555, null=True, blank=True)
    traceback = models.JSONField(null=True, blank=True)

    @classmethod
    def create(cls, message, e, creator):
        exc_type, exc_value, exc_traceback = sys.exc_info()
        obj = cls()
        obj.message = message
        obj.exception_msg = str(e)[:555]
        obj.traceback = [
            str(item)
            for item in traceback.extract_tb(exc_traceback)
        ]
        obj.exception_type = str(type(e))
        obj.creator = creator
        obj.save()
        return obj


class XMLDocPid(CommonControlField):
    journal = models.ForeignKey('XMLJournal', on_delete=models.SET_NULL, null=True, blank=True)
    issue = models.ForeignKey('XMLIssue', on_delete=models.SET_NULL, null=True, blank=True)
    related_items = models.ManyToManyField('self', symmetrical=False, related_name='related_to')
    aop_xml_versions = models.ManyToManyField(MinioFile, related_name='aop_xml_versions')
    xml_versions = models.ManyToManyField(MinioFile, related_name='xml_versions')

    v3 = models.CharField(_("v3"), max_length=23, null=True, blank=True)
    v2 = models.CharField(_("v2"), max_length=23, null=True, blank=True)
    aop_pid = models.CharField(_("AOP PID"), max_length=23, null=True, blank=True)

    fpage = models.CharField(_("fpage"), max_length=10, null=True, blank=True)
    fpage_seq = models.CharField(_("fpage_seq"), max_length=10, null=True, blank=True)
    lpage = models.CharField(_("lpage"), max_length=10, null=True, blank=True)
    article_publication_date = models.DateField(_("Document Publication Date"), null=True, blank=True)
    main_toc_section = models.CharField(_("main_toc_section"), max_length=64, null=True, blank=True)
    main_doi = models.CharField(_("DOI"), max_length=265, null=True, blank=True)

    z_elocation_id = models.CharField(_("elocation_id"), max_length=64, null=True, blank=True)
    z_article_titles_texts = models.CharField(_("article_titles_texts"), max_length=64, null=True, blank=True)
    z_surnames = models.CharField(_("surnames"), max_length=64, null=True, blank=True)
    z_collab = models.CharField(_("collab"), max_length=64, null=True, blank=True)
    z_links = models.CharField(_("links"), max_length=64, null=True, blank=True)
    z_partial_body = models.CharField(_("partial_body"), max_length=64, null=True, blank=True)

    synchronized = models.BooleanField(null=True, blank=True, default=False)
    sync_failure = models.ForeignKey(
        SyncFailure, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        indexes = [
            models.Index(fields=['journal']),
            models.Index(fields=['issue']),
            models.Index(fields=['v3']),
            models.Index(fields=['v2']),
            models.Index(fields=['aop_pid']),
            models.Index(fields=['fpage']),
            models.Index(fields=['fpage_seq']),
            models.Index(fields=['lpage']),
            models.Index(fields=['article_publication_date']),
            models.Index(fields=['main_toc_section']),
            models.Index(fields=['z_elocation_id']),
            models.Index(fields=['main_doi']),
            models.Index(fields=['z_article_titles_texts']),
            models.Index(fields=['z_surnames']),
            models.Index(fields=['z_collab']),
            models.Index(fields=['z_links']),
            models.Index(fields=['z_partial_body']),
            models.Index(fields=['synchronized']),
            models.Index(fields=['sync_failure']),
        ]

    # ForeignKey
    # contributors
    # affiliations
    # funding-group (sponsors e process number)

    # lang dependent / ManyToMany
    # doi
    # toc_sections
    # kwd-groups
    # titles
    # abstracts
    # figs / lang
    # tables / lang
    # equations

    # counts
    # history
    # license

    # references | ManyToMany
    # Open Science indicators

    def __str__(self):
        return str(self.data)

    @classmethod
    def unsynchronized(cls):
        """
        Identifica no pid provider local os registros que não
        estão sincronizados com o pid provider remoto (central) e
        faz a sincronização, registrando o XML local no pid provider remoto
        """
        return cls.objects.filter(synchronized=False).iterator()

    @property
    def article_in_issue(self):
        try:
            return self.xml_with_pre.article_in_issue
        except exceptions.XMLDocPidXMLWithPreError:
            return None

    @property
    def xml_with_pre(self):
        if not hasattr(self, '_xml_with_pre') or not self._xml_with_pre:
            try:
                self._xml_with_pre = get_xml_with_pre_from_uri(self.xml_uri)
            except Exception as e:
                raise exceptions.XMLDocPidXMLWithPreError(
                    _("Unable to get xml with pre (XMLDocPid) {}: {} {}").format(
                        self.xml_uri, type(e), e
                    )
                )
        return self._xml_with_pre

    @property
    def data(self):
        return dict(
            xml_uri=self.xml_uri,
            v2=self.v2,
            aop_pid=self.aop_pid,
            v3=self.v3,
            created=self.created.isoformat(),
            updated=self.updated.isoformat(),
            synchronized=self.synchronized,
            journal=self.journal.data,
            issue=self.issue.data,
            is_aop=self.is_aop,
        )

    @property
    def is_aop(self):
        if self.issue:
            return False
        if self.aop_pid:
            return True

    @property
    def xml_uri(self):
        if self.latest_version:
            return self.latest_version.uri

    @property
    def latest_version(self):
        if self.xml_versions.count() > 0:
            return self.xml_versions.latest('created')
        if self.aop_xml_versions.count() > 0:
            return self.aop_xml_versions.latest('created')

    def add_version(self, version):
        if self.is_aop:
            return self.aop_xml_versions.add(version)
        else:
            return self.xml_versions.add(version)

    @classmethod
    def get_xml_uri(cls, v3):
        try:
            item = cls.objects.get(v3=v3)
        except cls.DoesNotExist:
            return None
        else:
            return item.xml_uri

    @classmethod
    def register(cls, xml_with_pre, filename, user,
                 register_pid_provider_xml, synchronized=None):
        """
        Evaluate the XML data and returns corresponding PID v3, v2, aop_pid

        Parameters
        ----------
        xml : XMLWithPre
        filename : str
        user : User

        Returns
        -------
            dict or None
                {"registered": XMLArticle.data, "xml_changed": boolean,
                 "error": str(ForbiddenXMLDocPidRegistrationError)}
        Raises
        ------
        exceptions.XMLDocPidRegisterError
        exceptions.ForbiddenXMLDocPidRegistrationError
        PushPidProviderXMLError

        """
        try:
            logging.info("XMLDocPid.register {}".format(filename))

            # adaptador do xml with pre
            logging.info("XMLDocPid {} {} {}".format(
                xml_with_pre.v3, xml_with_pre.v2, xml_with_pre.aop_pid))
            xml_adapter = xml_sps_adapter.XMLAdapter(xml_with_pre)

            # obtém item registrado
            registered = cls._query_document(xml_adapter)
            logging.info(registered)
            if registered and xml_adapter.is_aop and not registered.is_aop:
                # levanta exceção se está requisitando pid para um XML contendo
                # dados de AOP, mas artigo já foi publicado em fascículo
                logging.exception(e)
                raise exceptions.ForbiddenXMLDocPidRegistrationError(
                    _("The XML content is an ahead of print version "
                      "but the document {} is already published in an issue"
                      ).format(registered)
                )

            # verfica os PIDs encontrados no XML / atualiza-os se necessário
            xml_changed = cls._complete_pids(xml_adapter, registered)
            logging.info("XMLDocPid xml_changed %s" % xml_changed)

            if registered:
                if registered.is_aop and not xml_adapter.is_aop:
                    # mudou de AOP para VOR, atualizar
                    registered._add_issue(xml_adapter, user)
                    logging.info("XMLDocPid add_issue %s" % registered)
            else:
                # cria registro
                registered = cls._register_new(xml_adapter, user)
                logging.info("XMLDocPid new %s" % registered)

            if registered:
                register_pid_provider_xml(
                    registered,
                    filename,
                    xml_adapter.tostring(),
                    user,
                )
                registered.set_synchronized(synchronized, user)
                return {"registered": registered.data, "xml_changed": xml_changed}

        except PushPidProviderXMLError as e:
            raise e
        except exceptions.ForbiddenXMLDocPidRegistrationError as e:
            logging.exception(e)
            return {"error": str(e)}

        except Exception as e:
            logging.exception(e)
            raise exceptions.XMLDocPidRegisterError(
                _("Unable to request document IDs for {} {} {}").format(
                    filename, type(e), str(e))
            )

    def set_synchronized(self, value, user):
        self.synchronized = value
        self.updated_by = user
        self.updated = datetime.utcnow()
        self.save()

    @classmethod
    def get_registration_demand(cls, xml_with_pre):
        """
        Verifica se há necessidade de registrar local e/ou remotamente
        """
        required_remote = True
        required_local = True

        xml_adapter = xml_sps_adapter.XMLAdapter(xml_with_pre)
        registered = cls._query_document(xml_adapter)
        equal = False
        if registered:
            equal = bool(
                registered.latest_version and
                registered.latest_version.finger_print == xml_with_pre.finger_print
            )
            if equal:
                # skip local registration
                required_local = False
                required_remote = not registered.synchronized

        return dict(
            registered=registered and registered.data or {},
            required_local=required_local,
            required_remote=required_remote,
        )

    @classmethod
    def get_registered(cls, xml_with_pre):
        """
        Get registered

        Parameters
        ----------
        xml_with_pre : XMLWithPre

        Returns
        -------
            None or XMLDocPid.data (dict)

        Raises
        ------
        exceptions.GetRegisteredError

        """
        try:
            # adaptador do xml with pre
            xml_adapter = xml_sps_adapter.XMLAdapter(xml_with_pre)
            registered = cls._query_document(xml_adapter)
            if registered:
                return registered.data
        except Exception as e:
            LOGGER.exception(e)
            raise exceptions.GetRegisteredError(
                _("Unable to get registered item {} {} {}").format(
                    xml_with_pre, type(e), e,
                )
            )

    @classmethod
    def _query_document(cls, xml_adapter):
        """
        Query document

        Arguments
        ---------
        xml_adapter : XMLAdapter

        Returns
        -------
        None or XMLArticle

        # Raises
        # ------
        # XMLArticle.MultipleObjectsReturned
        """
        LOGGER.info("xml_adapter.is_aop: %s" % xml_adapter.is_aop)
        if xml_adapter.is_aop:
            # o documento de entrada é um AOP
            try:
                # busca este documento na versão publicada em fascículo,
                # SEM dados de fascículo
                params = _query_document_args(xml_adapter, aop_version=False)
                return cls.objects.get(**params)
            except cls.DoesNotExist:
                try:
                    # busca este documento na versão publicada como AOP
                    params = _query_document_args(xml_adapter, aop_version=True)
                    return cls.objects.get(**params)
                except cls.DoesNotExist:
                    return None
            except Exception as e:
                raise exceptions.QueryDocumentError(
                    _("Unable to query document {} {} {}").format(
                        xml_adapter, type(e), str(e)))

        else:
            # o documento de entrada contém dados de issue
            try:
                # busca este documento na versão publicada em fascículo,
                # COM dados de fascículo
                params = _query_document_args(xml_adapter, filter_by_issue=True)
                return cls.objects.get(**params)
            except cls.DoesNotExist:
                try:
                    # busca este documento na versão publicada como AOP,
                    # SEM dados de fascículo,
                    # pois este pode ser uma atualização da versão AOP
                    params = _query_document_args(xml_adapter, aop_version=True)
                    return cls.objects.get(**params)
                except cls.DoesNotExist:
                    return None
            except Exception as e:
                raise exceptions.QueryDocumentError(
                    _("Unable to query document {} {} {}").format(
                        xml_adapter, type(e), str(e)))

    @classmethod
    def _register_new(cls, xml_adapter, user):
        try:
            doc = cls()
            doc.journal = XMLJournal.get_or_create(
                xml_adapter.journal_issn_electronic,
                xml_adapter.journal_issn_print,
            )
            if xml_adapter.is_aop:
                doc.issue = None
            else:
                doc.issue = XMLIssue.get_or_create(
                    doc.journal,
                    xml_adapter.issue.get("volume"),
                    xml_adapter.issue.get("number"),
                    xml_adapter.issue.get("suppl"),
                    xml_adapter.issue.get("pub_year"),
                )
                doc.fpage = xml_adapter.pages.get("fpage")
                doc.fpage_seq = xml_adapter.pages.get("fpage_seq")
                doc.lpage = xml_adapter.pages.get("lpage")

            for item in xml_adapter.related_items:
                try:
                    related = cls.objects.get(main_doi=item)
                except (cls.DoesNotExist, KeyError):
                    pass
                else:
                    doc.related_items.add(related)

            doc.article_publication_date = xml_adapter.article_publication_date
            doc.v3 = xml_adapter.v3
            doc.v2 = xml_adapter.v2
            doc.aop_pid = xml_adapter.aop_pid

            doc.main_doi = xml_adapter.main_doi
            doc.main_toc_section = xml_adapter.main_toc_section
            doc.z_article_titles_texts = xml_adapter.article_titles_texts
            doc.z_surnames = xml_adapter.surnames
            doc.z_collab = xml_adapter.collab
            doc.z_links = xml_adapter.links
            doc.z_partial_body = xml_adapter.partial_body
            doc.z_elocation_id = xml_adapter.elocation_id

            doc.creator = user
            doc.save()
            return doc

        except Exception as e:
            LOGGER.exception(e)
            raise exceptions.RegisterNewPidError(
                _("Register new pid error: {} {} {}").format(
                    type(e), e, xml_adapter,
                )
            )

    def _add_issue(self, xml_adapter, user):
        try:
            self.issue = XMLIssue.get_or_create(
                self.journal,
                xml_adapter.issue.get("volume"),
                xml_adapter.issue.get("number"),
                xml_adapter.issue.get("suppl"),
                xml_adapter.issue.get("pub_year"),
            )
            self.fpage = xml_adapter.pages.get("fpage")
            self.fpage_seq = xml_adapter.pages.get("fpage_seq")
            self.lpage = xml_adapter.pages.get("lpage")

            for item in xml_adapter.related_items:
                try:
                    related = cls.objects.get(main_doi=item)
                except (cls.DoesNotExist, KeyError):
                    pass
                else:
                    self.related_items.add(related)

            self.article_publication_date = xml_adapter.article_publication_date
            self.v3 = xml_adapter.v3
            self.v2 = xml_adapter.v2
            self.aop_pid = xml_adapter.aop_pid

            self.main_doi = xml_adapter.main_doi
            self.main_toc_section = xml_adapter.main_toc_section
            self.z_article_titles_texts = xml_adapter.article_titles_texts
            self.z_surnames = xml_adapter.surnames
            self.z_collab = xml_adapter.collab
            self.z_links = xml_adapter.links
            self.z_partial_body = xml_adapter.partial_body
            self.z_elocation_id = xml_adapter.elocation_id

            self.updated_by = user
            self.updated = datetime.utcnow()
            self.save()
            return doc

        except Exception as e:
            LOGGER.exception(e)
            raise exceptions.AddIssueError(
                _("Add issue error: {} {} {}").format(
                    type(e), e, xml_adapter,
                )
            )

    @classmethod
    def _get_unique_v3(cls):
        """
        Generate v3 and return it only if it is new

        Returns
        -------
            str
        """
        while True:
            generated = v3_gen.generates()
            if not cls._is_registered_pid(v3=generated):
                return generated

    @classmethod
    def _is_registered_pid(cls, v2=None, v3=None, aop_pid=None):
        if v3:
            kwargs = {'v3': v3}
        elif v2:
            kwargs = {'v2': v2}
        elif aop_pid:
            kwargs = {'aop_pid': aop_pid}

        if kwargs:
            try:
                found = cls.objects.filter(**kwargs)[0]
            except IndexError:
                return False
            else:
                return True

    @classmethod
    def _v2_generates(cls, xml_adapter):
        # '2022-10-19T13:51:33.830085'
        utcnow = datetime.utcnow()
        yyyymmddtime = "".join(
            [item for item in utcnow.isoformat() if item.isdigit()])
        mmdd = yyyymmddtime[4:8]
        nnnnn = str(utcnow.timestamp()).split(".")[0][-5:]
        return f"{xml_adapter.v2_prefix}{mmdd}{nnnnn}"

    @classmethod
    def _get_unique_v2(cls, xml_adapter):
        """
        Generate v2 and return it only if it is new

        Returns
        -------
            str
        """
        while True:
            generated = cls._v2_generates(xml_adapter)
            if not cls._is_registered_pid(v2=generated):
                return generated

    @classmethod
    def _complete_pids(cls, xml_adapter, registered):
        """
        Update `xml_adapter` pids with `registered` pids or
        create `xml_adapter` pids

        Parameters
        ----------
        xml_adapter: XMLAdapter
        registered: XMLArticle

        Returns
        -------
        bool

        """
        before = (xml_adapter.v2, xml_adapter.v3, xml_adapter.aop_pid)

        # adiciona os pids faltantes aos dados de entrada
        cls._add_pid_v3(xml_adapter, registered)
        cls._add_pid_v2(xml_adapter, registered)
        cls._add_aop_pid(xml_adapter, registered)

        after = (xml_adapter.v2, xml_adapter.v3, xml_adapter.aop_pid)

        LOGGER.info("%s %s" % (before, after))
        return before != after

    @classmethod
    def _add_pid_v3(cls, xml_adapter, registered):
        """
        Garante que xml_adapter tenha um v3 inédito

        Arguments
        ---------
        xml_adapter: XMLAdapter
        registered: XMLArticle

        """
        if registered:
            xml_adapter.v3 = registered.v3
        else:
            if not xml_adapter.v3 or cls._is_registered_pid(v3=xml_adapter.v3):
                xml_adapter.v3 = cls._get_unique_v3()

    @classmethod
    def _add_aop_pid(cls, xml_adapter, registered):
        """
        Atualiza xml_adapter com aop_pid se aplicável

        Arguments
        ---------
        xml_adapter: XMLAdapter
        registered: XMLArticle

        Returns
        -------
            dict
        """
        if registered:
            xml_adapter.aop_pid = registered.aop_pid

    @classmethod
    def _add_pid_v2(cls, xml_adapter, registered):
        """
        Adiciona a xml_adapter, v2 gerado ou recuperado de registered

        Arguments
        ---------
        xml_adapter: XMLAdapter
        registered: XMLArticle

        Returns
        -------
            dict
        """
        if registered:
            if registered.v2:
                xml_adapter.v2 = registered.v2
        if not xml_adapter.v2:
            xml_adapter.v2 = cls._get_unique_v2(xml_adapter)


def _set_isnull_parameters(kwargs):
    _kwargs = {}
    for k, v in kwargs.items():
        if v is None:
            _kwargs[f"{k}__isnull"] = True
        else:
            _kwargs[k] = v
    return _kwargs


def _query_document_args(xml_adapter, filter_by_issue=False, aop_version=False):
    """
    Get query parameters

    Arguments
    ---------
    xml_adapter : XMLAdapter
    filter_by_issue: bool
    aop_version: bool

    Returns
    -------
    dict
    """
    _params = dict(
        journal__issn_print=xml_adapter.journal_issn_print or None,
        journal__issn_electronic=xml_adapter.journal_issn_electronic or None,
        main_doi=xml_adapter.main_doi or None,
        z_surnames=xml_adapter.surnames or None,
        z_article_titles_texts=xml_adapter.article_titles_texts or None,
        z_collab=xml_adapter.collab or None,
        z_links=xml_adapter.links or None,
        z_elocation_id=xml_adapter.elocation_id,
    )

    if not any(_params.values()):
        # nenhum destes, então procurar pelo início do body
        if not xml_adapter.partial_body:
            LOGGER.exception(e)
            raise exceptions.NotEnoughParametersToGetDocumentRecordError(
                _("No attribute to use for disambiguations {} {} {}").format(
                    _params, type(e), e,
                )
            )
        _params["z_partial_body"] = xml_adapter.partial_body
    if aop_version:
        _params['issue__isnull'] = True
    else:
        if filter_by_issue:
            for k, v in xml_adapter.issue.items():
                _params[f"issue__{k}"] = v
            for k, v in xml_adapter.pages.items():
                _params[k] = v
    params = _set_isnull_parameters(_params)
    LOGGER.info(dict(filter_by_issue=filter_by_issue, aop_version=aop_version))
    LOGGER.info(params)
    return params
