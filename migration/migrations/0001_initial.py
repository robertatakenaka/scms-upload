# Generated by Django 4.1.10 on 2023-09-22 20:59

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import migration.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("issue", "0001_initial"),
        ("journal", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("collection", "0001_initial"),
        ("package", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="BodyAndBackFile",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Creation date"
                    ),
                ),
                (
                    "updated",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Last update date"
                    ),
                ),
                (
                    "pkg_name",
                    models.TextField(
                        blank=True, null=True, verbose_name="Package name"
                    ),
                ),
                (
                    "file",
                    models.FileField(
                        blank=True,
                        null=True,
                        upload_to=migration.models.body_and_back_directory_path,
                    ),
                ),
                ("version", models.IntegerField()),
                (
                    "creator",
                    models.ForeignKey(
                        editable=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(class)s_creator",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Creator",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(class)s_last_mod_user",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Updater",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="MigratedData",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Creation date"
                    ),
                ),
                (
                    "updated",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Last update date"
                    ),
                ),
                (
                    "pid",
                    models.CharField(
                        blank=True, max_length=23, null=True, verbose_name="PID"
                    ),
                ),
                (
                    "isis_updated_date",
                    models.CharField(
                        blank=True,
                        max_length=8,
                        null=True,
                        verbose_name="ISIS updated date",
                    ),
                ),
                (
                    "isis_created_date",
                    models.CharField(
                        blank=True,
                        max_length=8,
                        null=True,
                        verbose_name="ISIS created date",
                    ),
                ),
                ("data", models.JSONField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("TO_MIGRATE", "To migrate"),
                            ("TO_IGNORE", "To ignore"),
                            ("IMPORTED", "Imported"),
                        ],
                        default="TO_MIGRATE",
                        max_length=26,
                        verbose_name="Status",
                    ),
                ),
                (
                    "collection",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="collection.collection",
                    ),
                ),
                (
                    "creator",
                    models.ForeignKey(
                        editable=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(class)s_creator",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Creator",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(class)s_last_mod_user",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Updater",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="MigratedFile",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Creation date"
                    ),
                ),
                (
                    "updated",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Last update date"
                    ),
                ),
                (
                    "file",
                    models.FileField(
                        blank=True,
                        null=True,
                        upload_to=migration.models.migrated_files_directory_path,
                    ),
                ),
                (
                    "original_path",
                    models.TextField(
                        blank=True, null=True, verbose_name="Original Path"
                    ),
                ),
                (
                    "original_name",
                    models.TextField(
                        blank=True, null=True, verbose_name="Original name"
                    ),
                ),
                ("file_date", models.DateField()),
                (
                    "creator",
                    models.ForeignKey(
                        editable=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(class)s_creator",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Creator",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(class)s_last_mod_user",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Updater",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="AssetFile",
            fields=[
                (
                    "migratedfile_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="migration.migratedfile",
                    ),
                ),
                (
                    "original_href",
                    models.TextField(
                        blank=True, null=True, verbose_name="Original href"
                    ),
                ),
            ],
            bases=("migration.migratedfile",),
        ),
        migrations.CreateModel(
            name="MigratedDocument",
            fields=[
                (
                    "migrateddata_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="migration.migrateddata",
                    ),
                ),
                (
                    "pkg_name",
                    models.TextField(
                        blank=True, null=True, verbose_name="Package name"
                    ),
                ),
                ("missing_assets", models.JSONField(blank=True, null=True)),
                (
                    "file",
                    models.FileField(
                        blank=True,
                        null=True,
                        upload_to=migration.models.migrated_files_directory_path,
                    ),
                ),
                (
                    "xml_status",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("TO_GENERATE_XML", "To generate XML"),
                            ("GENERATED_XML", "GENERATED XML"),
                            ("TO_GENERATE_SPS_PKG", "To generate SPS Package"),
                            ("GENERATED_SPS_PKG", "GENERATED SPS PKG"),
                        ],
                        max_length=26,
                        null=True,
                        verbose_name="Status",
                    ),
                ),
            ],
            bases=("migration.migrateddata", models.Model),
        ),
        migrations.CreateModel(
            name="MigratedIssue",
            fields=[
                (
                    "migrateddata_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="migration.migrateddata",
                    ),
                ),
                (
                    "files_status",
                    models.CharField(
                        choices=[
                            ("TO_MIGRATE", "To migrate"),
                            ("TO_IGNORE", "To ignore"),
                            ("IMPORTED", "Imported"),
                        ],
                        default="TO_MIGRATE",
                        max_length=26,
                        verbose_name="Files Status",
                    ),
                ),
                (
                    "docs_status",
                    models.CharField(
                        choices=[
                            ("TO_MIGRATE", "To migrate"),
                            ("TO_IGNORE", "To ignore"),
                            ("IMPORTED", "Imported"),
                        ],
                        default="TO_MIGRATE",
                        max_length=26,
                        verbose_name="Documents Status",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
            bases=("migration.migrateddata",),
        ),
        migrations.CreateModel(
            name="MigratedJournal",
            fields=[
                (
                    "migrateddata_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="migration.migrateddata",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
            bases=("migration.migrateddata",),
        ),
        migrations.CreateModel(
            name="MigrationFailure",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Creation date"
                    ),
                ),
                (
                    "updated",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Last update date"
                    ),
                ),
                (
                    "action_name",
                    models.TextField(blank=True, null=True, verbose_name="Action"),
                ),
                (
                    "message",
                    models.TextField(blank=True, null=True, verbose_name="Message"),
                ),
                (
                    "migrated_item_name",
                    models.TextField(blank=True, null=True, verbose_name="Item name"),
                ),
                (
                    "migrated_item_id",
                    models.TextField(blank=True, null=True, verbose_name="Item id"),
                ),
                (
                    "exception_type",
                    models.TextField(
                        blank=True, null=True, verbose_name="Exception Type"
                    ),
                ),
                (
                    "exception_msg",
                    models.TextField(
                        blank=True, null=True, verbose_name="Exception Msg"
                    ),
                ),
                (
                    "collection_acron",
                    models.TextField(
                        blank=True, null=True, verbose_name="Collection acron"
                    ),
                ),
                ("traceback", models.JSONField(blank=True, null=True)),
                (
                    "creator",
                    models.ForeignKey(
                        editable=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(class)s_creator",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Creator",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(class)s_last_mod_user",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Updater",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Html2xmlReport",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Creation date"
                    ),
                ),
                (
                    "updated",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Last update date"
                    ),
                ),
                ("comments", models.TextField(blank=True, null=True)),
                (
                    "report",
                    models.FileField(
                        blank=True,
                        null=True,
                        upload_to=migration.models.generated_xml_report_directory_path,
                    ),
                ),
                ("empty_body", models.BooleanField(blank=True, null=True)),
                ("attention_demands", models.IntegerField(blank=True, null=True)),
                ("html_img_total", models.IntegerField(blank=True, null=True)),
                ("html_table_total", models.IntegerField(blank=True, null=True)),
                ("xml_supplmat_total", models.IntegerField(blank=True, null=True)),
                ("xml_media_total", models.IntegerField(blank=True, null=True)),
                ("xml_fig_total", models.IntegerField(blank=True, null=True)),
                ("xml_table_wrap_total", models.IntegerField(blank=True, null=True)),
                ("xml_eq_total", models.IntegerField(blank=True, null=True)),
                ("xml_graphic_total", models.IntegerField(blank=True, null=True)),
                (
                    "xml_inline_graphic_total",
                    models.IntegerField(blank=True, null=True),
                ),
                (
                    "xml_ref_elem_citation_total",
                    models.IntegerField(blank=True, null=True),
                ),
                (
                    "xml_ref_mixed_citation_total",
                    models.IntegerField(blank=True, null=True),
                ),
                ("xml_text_lang_total", models.IntegerField(blank=True, null=True)),
                (
                    "article_type",
                    models.CharField(blank=True, max_length=32, null=True),
                ),
                (
                    "creator",
                    models.ForeignKey(
                        editable=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(class)s_creator",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Creator",
                    ),
                ),
                (
                    "html",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="migration.bodyandbackfile",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(class)s_last_mod_user",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Updater",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="ClassicWebsiteConfiguration",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created",
                    models.DateTimeField(
                        auto_now_add=True, verbose_name="Creation date"
                    ),
                ),
                (
                    "updated",
                    models.DateTimeField(
                        auto_now=True, verbose_name="Last update date"
                    ),
                ),
                (
                    "title_path",
                    models.CharField(
                        blank=True,
                        help_text="Title path: title.id path or title.mst path without extension",
                        max_length=255,
                        null=True,
                        verbose_name="Title path",
                    ),
                ),
                (
                    "issue_path",
                    models.CharField(
                        blank=True,
                        help_text="Issue path: issue.id path or issue.mst path without extension",
                        max_length=255,
                        null=True,
                        verbose_name="Issue path",
                    ),
                ),
                (
                    "serial_path",
                    models.CharField(
                        blank=True,
                        help_text="Serial path",
                        max_length=255,
                        null=True,
                        verbose_name="Serial path",
                    ),
                ),
                (
                    "cisis_path",
                    models.CharField(
                        blank=True,
                        help_text="Cisis path where there are CISIS utilities such as mx and i2id",
                        max_length=255,
                        null=True,
                        verbose_name="Cisis path",
                    ),
                ),
                (
                    "bases_work_path",
                    models.CharField(
                        blank=True,
                        help_text="Bases work path",
                        max_length=255,
                        null=True,
                        verbose_name="Bases work path",
                    ),
                ),
                (
                    "bases_pdf_path",
                    models.CharField(
                        blank=True,
                        help_text="Bases translation path",
                        max_length=255,
                        null=True,
                        verbose_name="Bases pdf path",
                    ),
                ),
                (
                    "bases_translation_path",
                    models.CharField(
                        blank=True,
                        help_text="Bases translation path",
                        max_length=255,
                        null=True,
                        verbose_name="Bases translation path",
                    ),
                ),
                (
                    "bases_xml_path",
                    models.CharField(
                        blank=True,
                        help_text="Bases XML path",
                        max_length=255,
                        null=True,
                        verbose_name="Bases XML path",
                    ),
                ),
                (
                    "htdocs_img_revistas_path",
                    models.CharField(
                        blank=True,
                        help_text="Htdocs img revistas path",
                        max_length=255,
                        null=True,
                        verbose_name="Htdocs img revistas path",
                    ),
                ),
                (
                    "collection",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="collection.collection",
                    ),
                ),
                (
                    "creator",
                    models.ForeignKey(
                        editable=False,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(class)s_creator",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Creator",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="%(class)s_last_mod_user",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Updater",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="MigratedDocumentHTML",
            fields=[
                (
                    "migrateddocument_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="migration.migrateddocument",
                    ),
                ),
                (
                    "conversion_status",
                    models.CharField(
                        choices=[
                            ("TO_DO_HTML2XML", "to generate XML from HTML"),
                            (
                                "APPROVED_AUTOMATICALLY",
                                "generated XML is approved automatically",
                            ),
                            ("APPROVED", "generated XML is approved"),
                            ("REJECTED", "generated XML is rejected"),
                            ("NOT_EVALUATED", "generated XML is not evaluated"),
                        ],
                        default="NOT_EVALUATED",
                        max_length=25,
                        verbose_name="status",
                    ),
                ),
            ],
            bases=("migration.migrateddocument",),
        ),
        migrations.CreateModel(
            name="TranslationFile",
            fields=[
                (
                    "migratedfile_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="migration.migratedfile",
                    ),
                ),
                (
                    "part",
                    models.IntegerField(blank=True, null=True, verbose_name="Part"),
                ),
                (
                    "pkg_name",
                    models.TextField(
                        blank=True, null=True, verbose_name="Package name"
                    ),
                ),
                (
                    "lang",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="collection.language",
                    ),
                ),
            ],
            bases=("migration.migratedfile",),
        ),
        migrations.CreateModel(
            name="Rendition",
            fields=[
                (
                    "migratedfile_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="migration.migratedfile",
                    ),
                ),
                (
                    "pkg_name",
                    models.TextField(
                        blank=True, null=True, verbose_name="Package name"
                    ),
                ),
                (
                    "original_href",
                    models.TextField(
                        blank=True, null=True, verbose_name="Original href"
                    ),
                ),
                (
                    "lang",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="collection.language",
                    ),
                ),
            ],
            bases=("migration.migratedfile",),
        ),
        migrations.AddIndex(
            model_name="migrationfailure",
            index=models.Index(
                fields=["action_name"], name="migration_m_action__031324_idx"
            ),
        ),
        migrations.AddField(
            model_name="migratedjournal",
            name="scielo_journal",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="journal.scielojournal",
            ),
        ),
        migrations.AddField(
            model_name="migratedissue",
            name="asset_files",
            field=models.ManyToManyField(
                related_name="asset_files", to="migration.assetfile"
            ),
        ),
        migrations.AddField(
            model_name="migratedissue",
            name="migrated_journal",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="migration.migratedjournal",
            ),
        ),
        migrations.AddField(
            model_name="migratedissue",
            name="scielo_issue",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="issue.scieloissue",
            ),
        ),
        migrations.AddField(
            model_name="migratedfile",
            name="migrated_issue",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="migration.migratedissue",
            ),
        ),
        migrations.AddField(
            model_name="migrateddocument",
            name="migrated_issue",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="migration.migratedissue",
            ),
        ),
        migrations.AddField(
            model_name="migrateddocument",
            name="renditions",
            field=models.ManyToManyField(to="migration.rendition"),
        ),
        migrations.AddField(
            model_name="migrateddocument",
            name="sps_pkg",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="package.spspkg",
            ),
        ),
        migrations.AddIndex(
            model_name="migrateddata",
            index=models.Index(fields=["pid"], name="migration_m_pid_508b1a_idx"),
        ),
        migrations.AddIndex(
            model_name="migrateddata",
            index=models.Index(fields=["status"], name="migration_m_status_9aee95_idx"),
        ),
        migrations.AddIndex(
            model_name="migrateddata",
            index=models.Index(
                fields=["isis_updated_date"], name="migration_m_isis_up_c84dc4_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="classicwebsiteconfiguration",
            index=models.Index(
                fields=["collection"], name="migration_c_collect_99e14a_idx"
            ),
        ),
        migrations.AddField(
            model_name="bodyandbackfile",
            name="migrated_issue",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="migration.migratedissue",
            ),
        ),
        migrations.AddIndex(
            model_name="assetfile",
            index=models.Index(
                fields=["original_href"], name="migration_a_origina_eb4351_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="translationfile",
            index=models.Index(
                fields=["pkg_name"], name="migration_t_pkg_nam_4db04a_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="rendition",
            index=models.Index(
                fields=["original_href"], name="migration_r_origina_cc5aaa_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="rendition",
            index=models.Index(
                fields=["pkg_name"], name="migration_r_pkg_nam_a9bc60_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="migratedfile",
            index=models.Index(
                fields=["original_name"], name="migration_m_origina_3b6f90_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="migratedfile",
            index=models.Index(
                fields=["original_path"], name="migration_m_origina_ba75f0_idx"
            ),
        ),
        migrations.AddField(
            model_name="migrateddocumenthtml",
            name="bb_files",
            field=models.ManyToManyField(to="migration.bodyandbackfile"),
        ),
        migrations.AddField(
            model_name="migrateddocumenthtml",
            name="translation_files",
            field=models.ManyToManyField(to="migration.translationfile"),
        ),
        migrations.AddIndex(
            model_name="migrateddocument",
            index=models.Index(
                fields=["pkg_name"], name="migration_m_pkg_nam_2bd7db_idx"
            ),
        ),
        migrations.AddField(
            model_name="html2xmlreport",
            name="xml",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="migration.migrateddocumenthtml",
            ),
        ),
        migrations.AddIndex(
            model_name="bodyandbackfile",
            index=models.Index(
                fields=["pkg_name"], name="migration_b_pkg_nam_61bb9a_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="bodyandbackfile",
            index=models.Index(
                fields=["version"], name="migration_b_version_45e57b_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="migrateddocumenthtml",
            index=models.Index(
                fields=["conversion_status"], name="migration_m_convers_d17cb1_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="html2xmlreport",
            index=models.Index(
                fields=["attention_demands"], name="migration_h_attenti_94d6fe_idx"
            ),
        ),
    ]
