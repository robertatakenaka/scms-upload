# Generated by Django 3.2.12 on 2023-02-21 14:36

import core.models
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('migration', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='migratedxmlfile',
            name='assets_files',
        ),
        migrations.CreateModel(
            name='AssetInFile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True, verbose_name='Creation date')),
                ('updated', models.DateTimeField(auto_now=True, verbose_name='Last update date')),
                ('href', models.TextField(blank=True, null=True)),
                ('asset_file', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='migration.migratedassetfile')),
                ('creator', models.ForeignKey(editable=False, on_delete=models.SET(core.models.get_sentinel_user), related_name='assetinfile_creator', to=settings.AUTH_USER_MODEL, verbose_name='Creator')),
                ('updated_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='assetinfile_last_mod_user', to=settings.AUTH_USER_MODEL, verbose_name='Updater')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.AddField(
            model_name='migratedxmlfile',
            name='assets_in_xml',
            field=models.ManyToManyField(to='migration.AssetInFile'),
        ),
    ]
