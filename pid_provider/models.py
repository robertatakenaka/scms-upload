from datetime import datetime
from http import HTTPStatus
from shutil import copyfile
import hashlib
import logging

from django.db import models
from django.utils.translation import gettext as _
from wagtail.admin.edit_handlers import FieldPanel

from core.libs import xml_sps_lib
from core.models import CommonControlField
from files_storage.models import MinioFile
from . import xml_sps_adapter
from . import exceptions
from . import v3_gen


LOGGER = logging.getLogger(__name__)
LOGGER_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def utcnow():
    return datetime.utcnow()
    # return datetime.utcnow().isoformat().replace("T", " ") + "Z"


def is_equal_versions(latest, new_version):
    return latest and new_version.finger_print == latest.finger_print


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
    issn_electronic = models.CharField(_("issn_epub"), max_length=9, null=True, blank=True)
    issn_print = models.CharField(_("issn_ppub"), max_length=9, null=True, blank=True)

    def __str__(self):
        return f'{self.issn_electronic} {self.issn_print}'

    @classmethod
    def get_or_create(cls, issn_electronic, issn_print):
        try:
            params = {
                "issn_electronic": issn_electronic,
                "issn_print": issn_print,
            }
            kwargs = _set_isnull_parameters(params)
            logging.info("Search {}".format(kwargs))
            return cls.objects.get(**kwargs)
        except cls.DoesNotExist:
            params = {k: v for k, v in params.items() if v}
            logging.info("Create {}".format(params))
            journal = cls(**params)
            journal.save()
            return journal

    class Meta:
        unique_together = [
            ['issn_electronic', 'issn_print'],
        ]
        indexes = [
            models.Index(fields=['issn_electronic']),
            models.Index(fields=['issn_print']),
        ]


class XMLIssue(models.Model):
    volume = models.CharField(_("volume"), max_length=10, null=True, blank=True)
    number = models.CharField(_("number"), max_length=10, null=True, blank=True)
    suppl = models.CharField(_("suppl"), max_length=10, null=True, blank=True)
    pub_year = models.IntegerField(_("pub_year"), null=False)
    journal = models.ForeignKey('XMLJournal', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f'{self.journal} {self.volume or ""} {self.number or ""} {self.suppl or ""}'

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
            logging.info("Search {}".format(kwargs))
            return cls.objects.get(**kwargs)
        except cls.DoesNotExist:
            params = {k: v for k, v in params.items() if v}
            logging.info("Create {}".format(params))
            issue = cls(**params)
            issue.save()
            return issue

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


class BaseArticle(CommonControlField):
    v3 = models.CharField(_("v3"), max_length=23, null=True, blank=True)
    main_doi = models.CharField(_("main_doi"), max_length=265, null=True, blank=True)
    elocation_id = models.CharField(_("elocation_id"), max_length=23, null=True, blank=True)
    article_titles_texts = models.CharField(_("article_titles_texts"), max_length=64, null=True, blank=True)
    surnames = models.CharField(_("surnames"), max_length=64, null=True, blank=True)
    collab = models.CharField(_("collab"), max_length=64, null=True, blank=True)
    links = models.CharField(_("links"), max_length=64, null=True, blank=True)
    partial_body = models.CharField(_("partial_body"), max_length=64, null=True, blank=True)
    versions = models.ManyToManyField(MinioFile)

    @property
    def xml_uri(self):
        if self.latest_version:
            return self.latest_version.uri

    @property
    def latest_version(self):
        if self.versions.count():
            return self.versions.latest('created')

    def add_version(self, version):
        if version:
            if is_equal_versions(self.latest_version, version):
                return
            self.versions.add(version)

    def __str__(self):
        return f'{self.v3}'

    class Meta:
        indexes = [
            models.Index(fields=['v3']),
            models.Index(fields=['main_doi']),
            models.Index(fields=['article_titles_texts']),
            models.Index(fields=['surnames']),
            models.Index(fields=['collab']),
            models.Index(fields=['links']),
            models.Index(fields=['partial_body']),
            models.Index(fields=['elocation_id']),
        ]


class XMLAOPArticle(BaseArticle):
    journal = models.ForeignKey('XMLJournal', on_delete=models.SET_NULL, null=True, blank=True)
    aop_pid = models.CharField(_("aop_pid"), max_length=23, null=True, blank=True)
    published_in_issue = models.ForeignKey('XMLArticle', on_delete=models.SET_NULL, null=True, blank=True)

    @property
    def is_aop(self):
        return True

    def __str__(self):
        return f'{self.journal} {self.v3 or ""} {self.uri or ""}'

    class Meta:
        indexes = [
            models.Index(fields=['journal']),
            models.Index(fields=['aop_pid']),
            models.Index(fields=['published_in_issue']),
        ]


class XMLArticle(BaseArticle):
    v2 = models.CharField(_("v2"), max_length=23, null=True, blank=True)
    issue = models.ForeignKey('XMLIssue', on_delete=models.SET_NULL, null=True, blank=True)
    fpage = models.CharField(_("fpage"), max_length=10, null=True, blank=True)
    fpage_seq = models.CharField(_("fpage_seq"), max_length=10, null=True, blank=True)
    lpage = models.CharField(_("lpage"), max_length=10, null=True, blank=True)

    @property
    def is_aop(self):
        return False

    def __str__(self):
        return f'{self.issue and self.issue.journal or ""} {self.v3 or ""}'

    class Meta:
        indexes = [
            models.Index(fields=['v2']),
            models.Index(fields=['issue']),
            models.Index(fields=['fpage']),
            models.Index(fields=['fpage_seq']),
            models.Index(fields=['lpage']),
        ]


class AOP(CommonControlField):
    aop_pid = models.CharField(_("aop_pid"), max_length=23, null=True, blank=True)
    versions = models.ManyToManyField(MinioFile)

    def __str__(self):
        return self.aop_pid

    @classmethod
    def get_or_create(cls, aop_pid, user):
        try:
            return cls.objects.get(aop_pid=aop_pid)
        except cls.DoesNotExist:
            obj = cls()
            obj.aop_pid = aop_pid
            obj.creator = user
            obj.save()
            return obj

    @property
    def xml_uri(self):
        if self.latest_version:
            return self.latest_version.uri

    @property
    def latest_version(self):
        if self.versions.count():
            return self.versions.latest('created')

    def add_version(self, version):
        if version:
            if is_equal_versions(self.latest_version, version):
                return
            self.versions.add(version)

    class Meta:
        indexes = [
            models.Index(fields=['aop_pid']),
        ]


class VOR(CommonControlField):
    v2 = models.CharField(_("v2"), max_length=23, null=True, blank=True)
    issue = models.ForeignKey('XMLIssue', on_delete=models.SET_NULL, null=True, blank=True)
    fpage = models.CharField(_("fpage"), max_length=10, null=True, blank=True)
    fpage_seq = models.CharField(_("fpage_seq"), max_length=10, null=True, blank=True)
    lpage = models.CharField(_("lpage"), max_length=10, null=True, blank=True)
    versions = models.ManyToManyField(MinioFile)

    def __str__(self):
        return f'{self.issue or ""} {self.v2 or ""}'

    @classmethod
    def get_or_create(cls, v2, issue, fpage=None, fpage_seq=None,
                      lpage=None, creator=None):
        try:
            return cls.objects.get(v2=v2)
        except cls.DoesNotExist:
            obj = cls()
            obj.v2 = v2
            obj.issue = issue
            obj.fpage = fpage or None
            obj.fpage_seq = fpage_seq or None
            obj.lpage = lpage or None
            obj.creator = creator
            obj.save()
            return obj

    @property
    def xml_uri(self):
        if self.latest_version:
            return self.latest_version.uri

    @property
    def latest_version(self):
        if self.versions.count():
            return self.versions.latest('created')

    def add_version(self, version):
        if version:
            if is_equal_versions(self.latest_version, version):
                return
            self.versions.add(version)

    class Meta:
        indexes = [
            models.Index(fields=['v2']),
            models.Index(fields=['issue']),
            models.Index(fields=['fpage']),
            models.Index(fields=['fpage_seq']),
            models.Index(fields=['lpage']),
        ]


class PidV3(CommonControlField):
    v3 = models.CharField(_("v3"), max_length=23, null=True, blank=True)
    main_doi = models.CharField(_("main_doi"), max_length=265, null=True, blank=True)
    elocation_id = models.CharField(_("elocation_id"), max_length=23, null=True, blank=True)
    article_titles_texts = models.CharField(_("article_titles_texts"), max_length=64, null=True, blank=True)
    surnames = models.CharField(_("surnames"), max_length=64, null=True, blank=True)
    collab = models.CharField(_("collab"), max_length=64, null=True, blank=True)
    links = models.CharField(_("links"), max_length=64, null=True, blank=True)
    partial_body = models.CharField(_("partial_body"), max_length=64, null=True, blank=True)
    journal = models.ForeignKey('XMLJournal', on_delete=models.SET_NULL, null=True, blank=True)
    aop = models.ForeignKey(AOP, on_delete=models.SET_NULL, null=True, blank=True)
    vor = models.ForeignKey(VOR, on_delete=models.SET_NULL, null=True, blank=True)
    synchronized = models.BooleanField(null=True, blank=True, default=False)

    @property
    def is_aop(self):
        if self.vor:
            return False
        if self.aop:
            return True

    @property
    def aop_pid(self):
        if self.aop:
            self.aop.aop_pid

    @property
    def v2(self):
        if self.vor:
            self.vor.v2

    @property
    def xml_uri(self):
        if self.latest_version:
            return self.latest_version.uri

    @property
    def latest_version(self):
        if self.vor:
            return self.vor.latest_version
        if self.aop:
            return self.aop.latest_version

    def add_version(self, version):
        if self.vor:
            return self.vor.add_version(version)
        return self.aop.add_version(version)

    def __str__(self):
        return f'{self.v3}'

    @classmethod
    def get_xml_uri(cls, v3):
        try:
            return cls.objects.get(v3=v3).xml_uri
        except cls.DoesNotExist:
            return None

    @classmethod
    def request_document_ids(cls, xml_with_pre, filename, user,
                             register_pid_provider_xml, synchronized=None):
        """
        Request PID v3

        Parameters
        ----------
        xml : XMLWithPre
        filename : str
        user : User

        Returns
        -------
            dict or None
                {"registered": PidV3, "pids_updated": boolean}
        Raises
        ------
        exceptions.RequestDocumentIDsError
        exceptions.ForbiddenPidRequestError

        """
        try:
            logging.info("request_document_ids for {}".format(filename))

            # adaptador do xml with pre
            xml_adapter = xml_sps_adapter.XMLAdapter(xml_with_pre)

            # obtém item registrado
            registered = cls._query_document(xml_adapter)

            if registered and xml_adapter.is_aop and not registered.is_aop:
                # levanta exceção se está requisitando pid para um XML contendo
                # dados de AOP, mas artigo já foi publicado em fascículo
                logging.exception(e)
                raise exceptions.ForbiddenPidRequestError(
                    _("The XML content is an ahead of print version "
                      "but the document {} is already published in an issue"
                      ).format(registered)
                )

            # verfica os PIDs encontrados no XML / atualiza-os se necessário
            xml_changed = cls._complete_pids(xml_adapter, registered)

            if not registered:
                # cria registro
                registered = cls._register_new_pid(xml_adapter, user)
                logging.info("new %s" % registered)

            if registered:
                registered.synchronized = synchronized
                register_pid_provider_xml(
                    registered,
                    filename,
                    xml_adapter.tostring(),
                    user,
                )
                return {"registered": registered, "xml_changed": xml_changed}

        except exceptions.ForbiddenPidRequestError as e:
            return {"error": str(e)}

        except Exception as e:
            logging.exception(e)
            raise exceptions.RequestDocumentIDsError(
                _("Unable to request document IDs for {} {} {}").format(
                    filename, type(e), str(e))
            )

    def set_synchronized(self, value):
        self.synchronized = value
        self.updated_by = self.creator
        self.updated = datetime.utcnow()
        self.save()

    def is_equal_to(self, xml_with_pre):
        if self.latest_version:
            return self.latest_version.finger_print == xml_with_pre.finger_print

    @classmethod
    def get_registered(cls, xml_with_pre):
        """
        Get registered

        Parameters
        ----------
        xml : XMLWithPre

        Returns
        -------
            None or PidV3

        Raises
        ------
        exceptions.GetRegisteredError

        """
        try:
            # adaptador do xml with pre
            xml_adapter = xml_sps_adapter.XMLAdapter(xml_with_pre)
            return cls._query_document(xml_adapter)
        except Exception as e:
            logging.exception(e)
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
        None or PidV3

        # Raises
        # ------
        # PidV3.MultipleObjectsReturned
        """
        logging.info("xml_adapter.is_aop: %s" % xml_adapter.is_aop)
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
    def _register_new_pid(cls, xml_adapter, user):
        try:
            journal = XMLJournal.get_or_create(
                xml_adapter.journal_issn_electronic,
                xml_adapter.journal_issn_print,
            )
            doc = cls()
            if xml_adapter.is_aop:
                doc.aop = AOP.get_or_create(xml_adapter.v2, user)
            else:
                doc.vor = VOR.get_or_create(
                    xml_adapter.v2,
                    XMLIssue.get_or_create(
                        journal,
                        xml_adapter.issue.get("volume"),
                        xml_adapter.issue.get("number"),
                        xml_adapter.issue.get("suppl"),
                        xml_adapter.issue.get("pub_year"),
                    ),
                    xml_adapter.pages.get("fpage"),
                    xml_adapter.pages.get("fpage_seq"),
                    xml_adapter.pages.get("lpage"),
                    user,
                )
            doc.journal = journal
            doc.v3 = xml_adapter.v3
            doc.main_doi = xml_adapter.main_doi
            doc.article_titles_texts = xml_adapter.article_titles_texts
            doc.surnames = xml_adapter.surnames
            doc.collab = xml_adapter.collab
            doc.links = xml_adapter.links
            doc.partial_body = xml_adapter.partial_body
            doc.elocation_id = xml_adapter.pages.get("elocation_id")
            doc.creator = user
            doc.save()
            return doc

        except Exception as e:
            logging.exception(e)
            raise exceptions.RegisterNewPidError(
                _("Register new pid error: {} {} {}").format(
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
            kwargs = {'vor__v2': v2}
        elif aop_pid:
            kwargs = {'aop__aop_pid': aop_pid}

        if kwargs:
            try:
                found = cls.objects.filter(**kwargs)[0]
            except IndexError:
                return False
            else:
                return True

    @classmethod
    def _v2_generates(xml_adapter):
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
        registered: PidV3

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

        logging.info("%s %s" % (before, after))
        return old != new

    @classmethod
    def _add_pid_v3(cls, xml_adapter, registered):
        """
        Garante que xml_adapter tenha um v3 inédito

        Arguments
        ---------
        xml_adapter: XMLAdapter
        registered: PidV3

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
        registered: PidV3

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
        registered: PidV3

        Returns
        -------
            dict
        """
        if registered:
            if registered.v2:
                xml_adapter.v2 = registered.v2
        if not xml_adapter.v2:
            xml_adapter.v2 = cls._get_unique_v2(xml_adapter)

    class Meta:
        indexes = [
            models.Index(fields=['v3']),
            models.Index(fields=['aop']),
            models.Index(fields=['vor']),
            models.Index(fields=['main_doi']),
            models.Index(fields=['article_titles_texts']),
            models.Index(fields=['surnames']),
            models.Index(fields=['collab']),
            models.Index(fields=['links']),
            models.Index(fields=['partial_body']),
            models.Index(fields=['elocation_id']),
        ]


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
    aop_version: bool
    filter_by_issue: bool

    Returns
    -------
    dict
    """
    _params = dict(
        surnames=xml_adapter.surnames or None,
        article_titles_texts=xml_adapter.article_titles_texts or None,
        collab=xml_adapter.collab or None,
        links=xml_adapter.links or None,
        main_doi=xml_adapter.main_doi or None,
    )
    if not any(_params.values()):
        # nenhum destes, então procurar pelo início do body
        if not xml_adapter.partial_body:
            logging.exception(e)
            raise exceptions.NotEnoughParametersToGetDocumentRecordError(
                _("No attribute to use for disambiguations {} {} {}").format(
                    _params, type(e), e,
                )
            )
        _params["partial_body"] = xml_adapter.partial_body
    if aop_version:
        _params['aop__isnull'] = False
        _params['journal__issn_print'] = xml_adapter.journal_issn_print
        _params['journal__issn_electronic'] = xml_adapter.journal_issn_electronic
    else:
        _params['vor__issue__journal__issn_print'] = xml_adapter.journal_issn_print
        _params['vor__issue__journal__issn_electronic'] = xml_adapter.journal_issn_electronic

        if filter_by_issue:
            for k, v in xml_adapter.issue.items():
                _params[f"vor__issue__{k}"] = v
            for k, v in xml_adapter.pages.items():
                if k == "elocation_id":
                    continue
                _params[f"vor__{k}"] = v

    params = _set_isnull_parameters(_params)
    logging.info(dict(filter_by_issue=filter_by_issue, aop_version=aop_version))
    logging.info(params)
    return params
