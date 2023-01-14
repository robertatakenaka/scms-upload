# Generated by Django 3.2.12 on 2023-01-13 23:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('xmlsps', '0002_auto_20230113_2345'),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='encodedxmlarticle',
            name='xmlsps_enco_z_main__1d0b74_idx',
        ),
        migrations.RemoveField(
            model_name='encodedxmlarticle',
            name='z_main_doi',
        ),
        migrations.AddField(
            model_name='encodedxmlarticle',
            name='main_doi',
            field=models.CharField(blank=True, max_length=265, null=True, verbose_name='DOI'),
        ),
        migrations.AddIndex(
            model_name='encodedxmlarticle',
            index=models.Index(fields=['main_doi'], name='xmlsps_enco_main_do_dbd135_idx'),
        ),
    ]
