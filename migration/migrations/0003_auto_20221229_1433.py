# Generated by Django 3.2.12 on 2022-12-29 14:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('migration', '0002_auto_20221223_1515'),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='migrateddata',
            name='migration_m_status_9aee95_idx',
        ),
        migrations.RemoveIndex(
            model_name='migrateddata',
            name='migration_m_isis_up_c84dc4_idx',
        ),
        migrations.AddIndex(
            model_name='documentmigration',
            index=models.Index(fields=['files_status'], name='migration_d_files_s_615ab1_idx'),
        ),
        migrations.AddIndex(
            model_name='issuemigration',
            index=models.Index(fields=['files_status'], name='migration_i_files_s_6c65bc_idx'),
        ),
    ]
