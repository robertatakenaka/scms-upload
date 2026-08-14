import os
import io
import zipfile
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile


from package.models import (
    now,
    get_minio_config,
    minio_push_file_content,
    update_zip_file,
    basic_xml_directory_path,
    pkg_directory_path,
    preview_page_directory_path,
    BasicXMLFile,
    SPSPkgComponent,
    SPSPkg,
    BasicXMLFileSaveError,
    XMLVersionXmlWithPreError,
    SPSPkgComponentCreateOrUpdateError,
    SPSPkgMultipleObjectReturnedException,
    MinioConfiguration,
)
from collection.models import Language

User = get_user_model()


class UtilityFunctionsTestCase(TestCase):
    def test_now_format(self):
        result = now()
        self.assertIsInstance(result, str)
        self.assertNotIn(":", result)
        self.assertNotIn(".", result)

    @patch("files_storage.models.MinioConfiguration.get_files_storage")
    def test_get_minio_config_success(self, mock_get_files_storage):
        mock_instance = MagicMock()
        mock_get_files_storage.return_value = mock_instance
        
        result = get_minio_config()
        mock_get_files_storage.assert_called_once_with(name="website")
        self.assertEqual(result, mock_instance)

    @patch("files_storage.models.MinioConfiguration.get_files_storage")
    def test_get_minio_config_failure(self, mock_get_files_storage):
        mock_get_files_storage.side_effect = Exception("Connection error")
        with self.assertRaises(MinioConfiguration.DoesNotExist):
            get_minio_config()

    def test_minio_push_file_content_failure(self):
        mock_minio = MagicMock()
        # Forçamos o mock a lançar a exceção
        mock_minio.fput_content.side_effect = Exception("Upload failure")
        
        # A função NÃO deve estourar a Exception, e sim retornar o dict com erro
        res = minio_push_file_content(mock_minio, b"content", "text/xml", "file.xml")
        
        self.assertIn("error_type", res)
        self.assertEqual(res["error_msg"], "Upload failure")

    def test_minio_push_file_content_failure(self):
        mock_minio = MagicMock()
        mock_minio.fput_content.side_effect = Exception("Upload failure")
        
        res = minio_push_file_content(mock_minio, b"content", "text/xml", "file.xml")
        self.assertIn("error_type", res)
        self.assertIn("error_msg", res)

    def test_update_zip_file(self):
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            zf.writestr("test.xml", "<old/>")
            zf.writestr("other.txt", "keep me")

        temp_zip = self.id() + "_test.zip"
        with open(temp_zip, "wb") as f:
            f.write(zip_buffer.getvalue())

        try:
            mock_xml_pre = MagicMock()
            mock_xml_pre.tostring.return_value = b"<new_xml/>"

            update_zip_file(temp_zip, "test.xml", mock_xml_pre)

            with zipfile.ZipFile(temp_zip, "r") as zf:
                self.assertEqual(zf.read("test.xml"), b"<new_xml/>")
                self.assertEqual(zf.read("other.txt"), b"keep me")
        finally:
            if os.path.exists(temp_zip):
                os.remove(temp_zip)

    def test_directory_paths(self):
        class DummyInstance:
            directory_path = "custom/path"
            sps_pkg_name = "sps-pkg-v1"

        class DummyChildInstance:
            sps_pkg = DummyInstance()

        self.assertEqual(basic_xml_directory_path(DummyInstance(), "file.xml"), "custom/path/file.xml")
        self.assertEqual(basic_xml_directory_path(object(), "abc-def.xml"), "sps_pkg/abc/def/abc-def.xml")
        self.assertEqual(basic_xml_directory_path(object(), "simple.xml"), "xml/simple.xml")
        self.assertEqual(pkg_directory_path(DummyInstance(), "file.zip"), "sps_pkg/sps/pkg/v1/file.zip")
        self.assertEqual(preview_page_directory_path(DummyChildInstance(), "preview.html"), "sps_pkg/sps/pkg/v1/preview.html")


# 1. Definimos a subclasse concreta para testes
class DummyBasicXMLFile(BasicXMLFile):
    class Meta:
        app_label = "package"


# 2. Usamos @override_settings para o Django reconhecer o modelo nos testes
class BasicXMLFileTestCase(TestCase):
    
    def setUp(self):
        # Instanciamos a subclasse concreta sem precisar de acesso ao banco
        self.xml_obj = DummyBasicXMLFile()
        self.xml_obj.file = MagicMock()
        self.xml_obj.file.path = "/tmp/test_file.xml"

    def test_str_representation(self):
        self.assertEqual(str(self.xml_obj), "/tmp/test_file.xml")

    @patch("package.models.XMLWithPre.create")
    def test_xml_with_pre_property_success(self, mock_create):
        mock_create.return_value = ["parsed_xml"]
        self.assertEqual(self.xml_obj.xml_with_pre, "parsed_xml")

    @patch("package.models.XMLWithPre.create")
    def test_xml_with_pre_property_error(self, mock_create):
        mock_create.side_effect = Exception("Parse error")
        with self.assertRaises(XMLVersionXmlWithPreError):
            _ = self.xml_obj.xml_with_pre

    @patch("package.models.delete_files")
    def test_save_and_delete_file(self, mock_delete):
        self.xml_obj.file.save = MagicMock()
        
        self.xml_obj.save_file("updated.xml", b"<updated/>", delete_existing=True)
        
        mock_delete.assert_called_with("/tmp/test_file.xml")
        self.xml_obj.file.save.assert_called_once()


class SPSPkgComponentTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="password")
        self.pkg = SPSPkg.objects.create(
            creator=self.user, sps_pkg_name="pkg-01", pid_v3="v3-1234")
        self.lang = Language.objects.create(creator=self.user, code2="pt")

    def test_autocomplete_and_data(self):
        component = SPSPkgComponent.objects.create(
            creator=self.user,
            sps_pkg=self.pkg,
            basename="image.jpg",
            uri="http://example.com/image.jpg",
            component_type="asset",
            lang=self.lang,
            xml_elem_id="img1",
        )
        self.assertIn("pkg-01", component.autocomplete_label())
        self.assertIn("image.jpg", component.autocomplete_label())
        
        data = component.data
        self.assertEqual(data["basename"], "image.jpg")
        self.assertEqual(data["lang"], "pt")

    def test_get_classmethod(self):
        comp = SPSPkgComponent.objects.create(
            creator=self.user,
            sps_pkg=self.pkg,
            basename="graphic.png",
            uri="http://example.com/graphic.png",
        )
        self.assertEqual(SPSPkgComponent.get(sps_pkg=self.pkg, uri="http://example.com/graphic.png"), comp)
        self.assertEqual(SPSPkgComponent.get(sps_pkg=self.pkg, basename="graphic.png"), comp)
        with self.assertRaises(ValueError):
            SPSPkgComponent.get()

    @patch("package.models.Language.get_or_create")
    def test_create_or_update(self, mock_lang_get_or_create):
        mock_lang_get_or_create.return_value = self.lang

        comp = SPSPkgComponent.create_or_update(
            user=self.user,
            sps_pkg=self.pkg,
            uri="http://example.com/file.pdf",
            basename="file.pdf",
            component_type="rendition",
            lang="pt",
        )

        self.assertEqual(comp.sps_pkg, self.pkg)
        self.assertEqual(comp.basename, "file.pdf")
        self.assertEqual(comp.creator, self.user)

        # Atualização do objeto existente
        comp_updated = SPSPkgComponent.create_or_update(
            user=self.user,
            sps_pkg=self.pkg,
            uri="http://example.com/file.pdf",
            basename="file.pdf",
            component_type="updated_rendition",
        )
        self.assertEqual(comp_updated.id, comp.id)
        self.assertEqual(comp_updated.updated_by, self.user)
        self.assertEqual(comp_updated.component_type, "updated_rendition")


class SPSPkgTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="pkguser", password="password")
        self.pkg = SPSPkg.objects.create(
            creator=self.user,
            sps_pkg_name="sps-12345-v1",
            pid_v3="v3-00001",
            pid_v2="v2-00001",
            registered_in_core=True,
            texts={"xml_langs": ["en"], "pdf_langs": ["en"]},
        )

    def test_fix_sps_pkg_name(self):
        with patch.object(SPSPkg, "xml_with_pre", new_callable=PropertyMock) as mock_xml_pre:
            mock_obj = MagicMock()
            mock_obj.sps_pkg_name = "sps-12345-v2"
            mock_xml_pre.return_value = mock_obj

            res = self.pkg.fix_sps_pkg_name(save=True)
            self.assertTrue(res)
            self.assertEqual(self.pkg.sps_pkg_name, "sps-12345-v2")

    def test_get_method_single_object(self):
        found = SPSPkg.get(pid_v3="v3-00001")
        self.assertEqual(found, self.pkg)

    def test_get_method_does_not_exist(self):
        with self.assertRaises(SPSPkg.DoesNotExist):
            SPSPkg.get(pid_v3="non-existent")

    def test_get_method_multiple_objects_returned(self):
        SPSPkg.objects.create(
            creator=self.user,
            sps_pkg_name="sps-12345-v1",
            pid_v3="v3-00001",
            pid_v2="v2-00001",
        )
        with self.assertRaises(SPSPkg.MultipleObjectsReturned):
            SPSPkg.get(pid_v3="v3-00001")

    def test_validate(self):
        self.pkg.texts = {"xml_langs": ["pt", "en"], "pdf_langs": ["pt", "en"]}
        self.pkg.validate(save=True)
        self.assertTrue(self.pkg.valid_texts)

        self.pkg.texts = {"xml_langs": ["pt", "en"], "pdf_langs": ["pt"]}
        self.pkg.validate(save=True)
        self.assertFalse(self.pkg.valid_texts)

    def test_subdir_property(self):
        self.pkg.sps_pkg_name = "123456789-extra-path"
        self.assertEqual(self.pkg.subdir, os.path.join("123456789", "extra/path"))

    @patch("package.models.minio_push_file_content")
    def test_upload_to_the_cloud(self, mock_push):
        mock_push.return_value = {"uri": "http://minio.local/file.png"}
        mock_minio = MagicMock()

        res = self.pkg.upload_to_the_cloud(
            user=self.user,
            minio=mock_minio,
            filename="test.png",
            ext=".png",
            content=b"bytes",
            component_type="asset",
        )

        self.assertEqual(res["uri"], "http://minio.local/file.png")
        self.assertTrue(SPSPkgComponent.objects.filter(basename="test.png").exists())

    @patch.object(SPSPkg, "upload_to_the_cloud")
    def test_upload_xml_to_the_cloud(self, mock_upload):
        mock_upload.return_value = {"uri": "http://minio.local/file.xml"}
        
        mock_xml_pre = MagicMock()
        mock_xml_pre.xmltree = MagicMock()
        # RETORNE UMA STRING AQUI (sem o 'b'):
        mock_xml_pre.tostring.return_value = "<xml/>"
        
        mock_minio = MagicMock()

        res = self.pkg.upload_xml_to_the_cloud(self.user, mock_minio, mock_xml_pre)
        self.assertEqual(self.pkg.xml_uri, "http://minio.local/file.xml")
        self.assertEqual(res, {"items": [{"uri": "http://minio.local/file.xml"}]})

    @patch.object(SPSPkg, "xml_with_pre", new_callable=PropertyMock)
    def test_pub_date(self, mock_xml_pre):
        mock_obj = MagicMock()
        mock_obj.article_publication_date = "2023-05-20"
        mock_xml_pre.return_value = mock_obj

        self.assertEqual(self.pkg.pub_date, "2023-05-20")

        mock_obj.article_publication_date = "2023-05"
        mock_obj.get_complete_publication_date.return_value = "2023-05-15"
        self.assertEqual(self.pkg.pub_date, "2023-05-15")

    def test_complete_pid_v2(self):
        pkg_without_pid_v2 = SPSPkg.objects.create(
            creator=self.user,
            sps_pkg_name="pkg-no-pid2",
            pid_v3="v3-999",
            file=SimpleUploadedFile("dummy.zip", b"zipcontent"),
        )
        
        with patch.object(SPSPkg, "xml_with_pre", new_callable=PropertyMock) as mock_xml_pre:
            mock_xml = MagicMock()
            mock_xml.v2 = "v2-generated"
            mock_xml_pre.return_value = mock_xml

            SPSPkg.complete_pid_v2(user=self.user, sps_pkg_id_list=[pkg_without_pid_v2.id])
            
            pkg_without_pid_v2.refresh_from_db()
            self.assertEqual(pkg_without_pid_v2.pid_v2, "v2-generated")
            self.assertEqual(pkg_without_pid_v2.updated_by, self.user)
