# Generated by Django 5.0.3 on 2024-08-03 20:52

import django.db.models.deletion
import wagtail.fields
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("article", "0002_remove_articleauthor_author_and_more"),
        ("collection", "0003_websiteconfigurationendpoint"),
        ("issue", "0005_tocsection_section_tocsection_toc_and_more"),
        ("journal", "0004_remove_journal_journal_acron_journal_acron_and_more"),
        ("package", "0003_remove_spspkg_components_remove_spspkg_scheduled_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="article",
            name="sections",
            field=models.ManyToManyField(
                to="journal.journalsection", verbose_name="sections"
            ),
        ),
        migrations.AddField(
            model_name="articletitle",
            name="language",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="collection.language",
            ),
        ),
        migrations.AddField(
            model_name="articletitle",
            name="text",
            field=wagtail.fields.RichTextField(default=""),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="article",
            name="article_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("abstract", "Abstract"),
                    ("addendum", "Addendum"),
                    ("announcement", "Announcement"),
                    ("article-commentary", "Article-Commentary"),
                    ("book-review", "Book-Review"),
                    ("books-received", "Books-Received"),
                    ("brief-report", "Brief-Report"),
                    ("calendar", "Calendar"),
                    ("case-report", "Case-Report"),
                    ("clinical-trial", "Clinical-Trial"),
                    ("collection", "Coleção"),
                    ("correction", "Correction"),
                    ("data-article", "Data-Article"),
                    ("discussion", "Discussion"),
                    ("dissertation", "Dissertation"),
                    ("editorial", "Editorial"),
                    ("editorial-material", "Editorial-Material"),
                    ("guideline", "Guideline"),
                    ("in-brief", "In-Brief"),
                    ("interview", "Interview"),
                    ("introduction", "Introduction"),
                    ("letter", "Letter"),
                    ("meeting-report", "Meeting-Report"),
                    ("news", "News"),
                    ("obituary", "Obituary"),
                    ("oration", "Oration"),
                    ("other", "Other"),
                    ("partial-retraction", "Partial-Retraction"),
                    ("product-review", "Product-Review"),
                    ("rapid-communication", "Rapid-Communication"),
                    ("reply", "Reply"),
                    ("reprint", "Reprint"),
                    ("research-article", "Research-Article"),
                    ("retraction", "Retraction"),
                    ("review-article", "Review-Article"),
                    ("technical-report", "Technical-Report"),
                    ("translation", "Translation"),
                ],
                max_length=32,
                null=True,
                verbose_name="Article type",
            ),
        ),
        migrations.AlterField(
            model_name="article",
            name="status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("erratum-submitted", "Erratum submitted"),
                    ("update-submitted", "Update submitted"),
                    ("required-update", "Required update"),
                    ("required-erratum", "Required erratum"),
                    ("prepare-to-publish", "Prepare to publish"),
                    ("ready-to-publish", "Ready to publish"),
                    ("scheduled-to-publish", "Scheduled to publish"),
                    ("published", "Publicado"),
                ],
                max_length=32,
                null=True,
                verbose_name="Article status",
            ),
        ),
        migrations.AddIndex(
            model_name="article",
            index=models.Index(fields=["status"], name="article_art_status_908632_idx"),
        ),
        migrations.DeleteModel(
            name="ArticleAuthor",
        ),
    ]