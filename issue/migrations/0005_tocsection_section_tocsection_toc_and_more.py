# Generated by Django 5.0.3 on 2024-08-03 20:52

import django.db.models.deletion
import modelcluster.fields
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("issue", "0004_issue_issue_pid_suffix_issue_order_toc_tocsection"),
        ("journal", "0004_remove_journal_journal_acron_journal_acron_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="tocsection",
            name="section",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="journal.journalsection",
            ),
        ),
        migrations.AddField(
            model_name="tocsection",
            name="toc",
            field=modelcluster.fields.ParentalKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="issue_sections",
                to="issue.toc",
            ),
        ),
        migrations.AddField(
            model_name="tocsection",
            name="updated_by",
            field=models.ForeignKey(
                blank=True,
                editable=False,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="%(class)s_last_mod_user",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Updater",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="tocsection",
            unique_together={("toc", "group", "section")},
        ),
    ]
