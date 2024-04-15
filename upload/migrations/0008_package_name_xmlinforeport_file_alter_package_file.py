# Generated by Django 5.0.3 on 2024-04-14 12:20

import upload.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("upload", "0007_alter_basexmlvalidationresult_validation_type_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="package",
            name="name",
            field=models.CharField(
                blank=True, max_length=32, null=True, verbose_name="SPS Package name"
            ),
        ),
        migrations.AddField(
            model_name="xmlinforeport",
            name="file",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to=upload.models.upload_package_directory_path,
                verbose_name="Report File",
            ),
        ),
        migrations.AlterField(
            model_name="package",
            name="file",
            field=models.FileField(
                upload_to=upload.models.upload_package_directory_path,
                verbose_name="Package File",
            ),
        ),
    ]
