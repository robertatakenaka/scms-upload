# Generated by Django 5.0.3 on 2024-07-09 17:22

import django.db.models.deletion
import modelcluster.fields
import wagtail.fields
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("collection", "0003_websiteconfigurationendpoint"),
        ("institution", "0001_initial"),
        ("journal", "0004_journalsection"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveField(
            model_name="journal",
            name="journal_acron",
        ),
        migrations.AddField(
            model_name="journal",
            name="submission_online_url",
            field=models.URLField(
                blank=True, null=True, verbose_name="Submission online URL"
            ),
        ),
        migrations.CreateModel(
            name="JournalCollection",
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
                    "journal",
                    modelcluster.fields.ParentalKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="journal_collections",
                        to="journal.journal",
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
            options={
                "verbose_name": "Journal collection",
                "verbose_name_plural": "Journal collections",
                "unique_together": {("journal", "collection")},
            },
        ),
        migrations.CreateModel(
            name="Sponsor",
            fields=[
                (
                    "institutionhistory_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="institution.institutionhistory",
                    ),
                ),
                (
                    "sort_order",
                    models.IntegerField(blank=True, editable=False, null=True),
                ),
                (
                    "journal",
                    modelcluster.fields.ParentalKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sponsor",
                        to="journal.journal",
                    ),
                ),
            ],
            options={
                "ordering": ["sort_order"],
                "abstract": False,
            },
            bases=("institution.institutionhistory", models.Model),
        ),
        migrations.CreateModel(
            name="Subject",
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
                ("code", models.CharField(blank=True, max_length=30, null=True)),
                ("value", models.CharField(blank=True, max_length=100, null=True)),
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
            options={
                "abstract": False,
            },
        ),
        migrations.AddField(
            model_name="journal",
            name="subject",
            field=models.ManyToManyField(
                blank=True, to="journal.subject", verbose_name="Study Areas"
            ),
        ),
        migrations.CreateModel(
            name="JournalHistory",
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
                    "year",
                    models.CharField(
                        blank=True, max_length=4, null=True, verbose_name="Event year"
                    ),
                ),
                (
                    "month",
                    models.CharField(
                        blank=True,
                        choices=[
                            (1, "JANUARY"),
                            (2, "FEBRUARY"),
                            (3, "MARCH"),
                            (4, "APRIL"),
                            (5, "MAY"),
                            (6, "JUNE"),
                            (7, "JULY"),
                            (8, "AUGUST"),
                            (9, "SEPTEMBER"),
                            (10, "OCTOBER"),
                            (11, "NOVEMBER"),
                            (12, "DECEMBER"),
                        ],
                        max_length=2,
                        null=True,
                        verbose_name="Event month",
                    ),
                ),
                (
                    "day",
                    models.CharField(
                        blank=True, max_length=2, null=True, verbose_name="Event day"
                    ),
                ),
                (
                    "event_type",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("ADMITTED", "Admitted to the collection"),
                            ("INTERRUPTED", "Indexing interrupted"),
                        ],
                        max_length=16,
                        null=True,
                        verbose_name="Event type",
                    ),
                ),
                (
                    "interruption_reason",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("ceased", "Ceased journal"),
                            ("not-open-access", "Not open access"),
                            ("suspended-by-committee", "by the committee"),
                            ("suspended-by-editor", "by the editor"),
                        ],
                        max_length=24,
                        null=True,
                        verbose_name="Indexing interruption reason",
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
                    "journal_collection",
                    modelcluster.fields.ParentalKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="journal_history",
                        to="journal.journalcollection",
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
            options={
                "verbose_name": "Collection journal event",
                "verbose_name_plural": "Collection journal events",
                "ordering": ("journal_collection", "-year", "-month", "-day"),
                "indexes": [
                    models.Index(
                        fields=["event_type"], name="journal_jou_event_t_693227_idx"
                    )
                ],
                "unique_together": {
                    ("journal_collection", "event_type", "year", "month", "day")
                },
            },
        ),
        migrations.CreateModel(
            name="Mission",
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
                ("text", wagtail.fields.RichTextField()),
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
                    "journal",
                    modelcluster.fields.ParentalKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="mission",
                        to="journal.journal",
                    ),
                ),
                (
                    "language",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="collection.language",
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
            options={
                "indexes": [
                    models.Index(
                        fields=["journal"], name="journal_mis_journal_386d75_idx"
                    )
                ],
            },
        ),
    ]
