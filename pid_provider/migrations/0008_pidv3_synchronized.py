# Generated by Django 3.2.12 on 2023-01-11 13:08

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pid_provider', '0007_vor_versions'),
    ]

    operations = [
        migrations.AddField(
            model_name='pidv3',
            name='synchronized',
            field=models.BooleanField(blank=True, default=False, null=True),
        ),
    ]
