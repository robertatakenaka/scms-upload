# Generated by Django 3.2.12 on 2022-09-17 13:57

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('journal', '0001_initial'),
        ('issue', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Collection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True, verbose_name='Creation date')),
                ('updated', models.DateTimeField(auto_now=True, verbose_name='Last update date')),
                ('acron', models.CharField(blank=True, max_length=255, null=True, verbose_name='Collection Acronym')),
                ('name', models.CharField(max_length=255, verbose_name='Collection Name')),
                ('creator', models.ForeignKey(editable=False, on_delete=django.db.models.deletion.CASCADE, related_name='collection_creator', to=settings.AUTH_USER_MODEL, verbose_name='Creator')),
                ('updated_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='collection_last_mod_user', to=settings.AUTH_USER_MODEL, verbose_name='Updater')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='SciELOJournal',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True, verbose_name='Creation date')),
                ('updated', models.DateTimeField(auto_now=True, verbose_name='Last update date')),
                ('scielo_issn', models.CharField(max_length=9, verbose_name='SciELO ISSN')),
                ('acron', models.CharField(blank=True, max_length=25, null=True, verbose_name='Acronym')),
                ('title', models.CharField(blank=True, max_length=255, null=True, verbose_name='Title')),
                ('publication_status', models.CharField(blank=True, choices=[('C', 'Current')], max_length=2, null=True, verbose_name='Publication Status')),
                ('collection', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='collection.collection')),
                ('creator', models.ForeignKey(editable=False, on_delete=django.db.models.deletion.CASCADE, related_name='scielojournal_creator', to=settings.AUTH_USER_MODEL, verbose_name='Creator')),
                ('updated_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='scielojournal_last_mod_user', to=settings.AUTH_USER_MODEL, verbose_name='Updater')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='SciELOIssue',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True, verbose_name='Creation date')),
                ('updated', models.DateTimeField(auto_now=True, verbose_name='Last update date')),
                ('issue_pid', models.CharField(max_length=17, verbose_name='Issue PID')),
                ('issue_folder', models.CharField(max_length=17, verbose_name='Issue Folder')),
                ('creator', models.ForeignKey(editable=False, on_delete=django.db.models.deletion.CASCADE, related_name='scieloissue_creator', to=settings.AUTH_USER_MODEL, verbose_name='Creator')),
                ('scielo_journal', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='collection.scielojournal')),
                ('updated_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='scieloissue_last_mod_user', to=settings.AUTH_USER_MODEL, verbose_name='Updater')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='SciELODocument',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True, verbose_name='Creation date')),
                ('updated', models.DateTimeField(auto_now=True, verbose_name='Last update date')),
                ('pid', models.CharField(blank=True, max_length=17, null=True, verbose_name='PID')),
                ('file_id', models.CharField(blank=True, max_length=17, null=True, verbose_name='File ID')),
                ('creator', models.ForeignKey(editable=False, on_delete=django.db.models.deletion.CASCADE, related_name='scielodocument_creator', to=settings.AUTH_USER_MODEL, verbose_name='Creator')),
                ('scielo_issue', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='collection.scieloissue')),
                ('updated_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='scielodocument_last_mod_user', to=settings.AUTH_USER_MODEL, verbose_name='Updater')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='JournalCollections',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True, verbose_name='Creation date')),
                ('updated', models.DateTimeField(auto_now=True, verbose_name='Last update date')),
                ('creator', models.ForeignKey(editable=False, on_delete=django.db.models.deletion.CASCADE, related_name='journalcollections_creator', to=settings.AUTH_USER_MODEL, verbose_name='Creator')),
                ('official_journal', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='journal.officialjournal')),
                ('scielo_journals', models.ManyToManyField(to='collection.SciELOJournal')),
                ('updated_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='journalcollections_last_mod_user', to=settings.AUTH_USER_MODEL, verbose_name='Updater')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='IssueInCollections',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True, verbose_name='Creation date')),
                ('updated', models.DateTimeField(auto_now=True, verbose_name='Last update date')),
                ('creator', models.ForeignKey(editable=False, on_delete=django.db.models.deletion.CASCADE, related_name='issueincollections_creator', to=settings.AUTH_USER_MODEL, verbose_name='Creator')),
                ('official_issue', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='issue.issue')),
                ('scielo_issues', models.ManyToManyField(to='collection.SciELOIssue')),
                ('updated_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='issueincollections_last_mod_user', to=settings.AUTH_USER_MODEL, verbose_name='Updater')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='DocumentInCollections',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True, verbose_name='Creation date')),
                ('updated', models.DateTimeField(auto_now=True, verbose_name='Last update date')),
                ('creator', models.ForeignKey(editable=False, on_delete=django.db.models.deletion.CASCADE, related_name='documentincollections_creator', to=settings.AUTH_USER_MODEL, verbose_name='Creator')),
                ('scielo_docs', models.ManyToManyField(to='collection.SciELODocument')),
                ('updated_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='documentincollections_last_mod_user', to=settings.AUTH_USER_MODEL, verbose_name='Updater')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
