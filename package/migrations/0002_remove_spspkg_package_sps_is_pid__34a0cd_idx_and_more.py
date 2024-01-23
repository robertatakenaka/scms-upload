# Generated by Django 4.2.6 on 2024-01-22 22:59

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("package", "0001_initial"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="spspkg",
            name="package_sps_is_pid__34a0cd_idx",
        ),
        migrations.RenameField(
            model_name="spspkg",
            old_name="is_pid_provider_synchronized",
            new_name="registered_in_core",
        ),
        migrations.RemoveField(
            model_name="spspkg",
            name="expected_components_total",
        ),
        migrations.RemoveField(
            model_name="spspkg",
            name="storaged_files_total",
        ),
        migrations.AddIndex(
            model_name="spspkg",
            index=models.Index(
                fields=["registered_in_core"], name="package_sps_registe_40fa05_idx"
            ),
        ),
    ]
