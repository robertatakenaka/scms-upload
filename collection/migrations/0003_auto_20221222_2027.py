# Generated by Django 3.2.12 on 2022-12-22 20:27

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('collection', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='filesstorageconfiguration',
            name='name',
            field=models.CharField(max_length=255, null=True, verbose_name='Name'),
        ),
        migrations.AddField(
            model_name='xmlfile',
            name='v3',
            field=models.CharField(blank=True, max_length=23, null=True, verbose_name='V3'),
        ),
        migrations.AddIndex(
            model_name='filesstorageconfiguration',
            index=models.Index(fields=['name'], name='collection__name_75c5f8_idx'),
        ),
        migrations.AddIndex(
            model_name='xmlfile',
            index=models.Index(fields=['v3'], name='collection__v3_4868de_idx'),
        ),
    ]