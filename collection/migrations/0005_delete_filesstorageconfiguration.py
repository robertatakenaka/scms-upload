# Generated by Django 3.2.12 on 2022-12-23 15:15

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('migration', '0002_auto_20221223_1515'),
        ('collection', '0004_auto_20221223_1515'),
    ]

    operations = [
        migrations.DeleteModel(
            name='FilesStorageConfiguration',
        ),
    ]