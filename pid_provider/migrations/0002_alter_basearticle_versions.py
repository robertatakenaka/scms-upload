# Generated by Django 3.2.12 on 2022-12-31 02:14

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('files_storage', '0003_auto_20221231_0214'),
        ('pid_provider', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='basearticle',
            name='versions',
            field=models.ManyToManyField(to='files_storage.FileVersions'),
        ),
    ]