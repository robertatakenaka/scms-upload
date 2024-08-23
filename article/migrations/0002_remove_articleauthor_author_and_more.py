# Generated by Django 5.0.3 on 2024-08-23 00:36

import django.db.models.deletion
import wagtail.fields
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("article", "0001_initial"),
        ("collection", "0003_websiteconfigurationendpoint"),
        ("issue", "0004_issue_issue_pid_suffix_issue_order_toc_tocsection"),
        ("journal", "0004_journal_contact_address_journal_contact_location_and_more"),
        ("package", "0003_remove_spspkg_components_remove_spspkg_scheduled_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveField(
            model_name="articleauthor",
            name="author",
        ),
        migrations.RemoveField(
            model_name="articleauthor",
            name="researcher_ptr",
        ),
        migrations.AlterModelOptions(
            name="article",
            options={
                "ordering": ["position", "fpage", "-first_publication_date"],
                "permissions": (
                    ("make_article_change", "Can make article change"),
                    ("request_article_change", "Can request article change"),
                ),
            },
        ),
        migrations.AlterModelOptions(
            name="articletitle",
            options={},
        ),
        migrations.RenameField(
            model_name="articletitle",
            old_name="title_with_lang",
            new_name="parent",
        ),
        migrations.RemoveField(
            model_name="articletitle",
            name="lang",
        ),
        migrations.RemoveField(
            model_name="articletitle",
            name="sort_order",
        ),
        migrations.RemoveField(
            model_name="articletitle",
            name="title",
        ),
        migrations.RemoveField(
            model_name="requestarticlechange",
            name="deadline",
        ),
        migrations.RemoveField(
            model_name="requestarticlechange",
            name="demanded_user",
        ),
        migrations.RemoveField(
            model_name="requestarticlechange",
            name="pid_v3",
        ),
        migrations.AddField(
            model_name="article",
            name="first_publication_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="article",
            name="pid_v2",
            field=models.CharField(
                blank=True, max_length=23, null=True, verbose_name="PID v2"
            ),
        ),
        migrations.AddField(
            model_name="article",
            name="position",
            field=models.PositiveSmallIntegerField(
                blank=True, null=True, verbose_name="Position"
            ),
        ),
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
        migrations.AlterField(
            model_name="requestarticlechange",
            name="comment",
            field=models.TextField(blank=True, null=True, verbose_name="Comment"),
        ),
        migrations.AddIndex(
            model_name="article",
            index=models.Index(fields=["status"], name="article_art_status_908632_idx"),
        ),
        migrations.DeleteModel(
            name="ArticleAuthor",
        ),
    ]
