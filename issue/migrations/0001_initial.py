# Generated by Django 3.2.12 on 2022-09-17 13:57

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('journal', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Issue',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', models.DateTimeField(auto_now_add=True, verbose_name='Creation date')),
                ('updated', models.DateTimeField(auto_now=True, verbose_name='Last update date')),
                ('year', models.CharField(max_length=4, verbose_name='Publication Year')),
                ('volume', models.CharField(blank=True, max_length=255, null=True, verbose_name='Volume')),
                ('number', models.CharField(blank=True, max_length=255, null=True, verbose_name='Number')),
                ('supplement', models.CharField(blank=True, max_length=255, null=True, verbose_name='Supplement')),
                ('creator', models.ForeignKey(editable=False, on_delete=django.db.models.deletion.CASCADE, related_name='issue_creator', to=settings.AUTH_USER_MODEL, verbose_name='Creator')),
                ('official_journal', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='journal.officialjournal')),
                ('updated_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='issue_last_mod_user', to=settings.AUTH_USER_MODEL, verbose_name='Updater')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
