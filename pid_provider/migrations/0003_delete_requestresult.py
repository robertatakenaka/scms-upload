# Generated by Django 3.2.12 on 2022-12-31 16:22

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pid_provider', '0002_alter_basearticle_versions'),
    ]

    operations = [
        migrations.DeleteModel(
            name='RequestResult',
        ),
    ]
