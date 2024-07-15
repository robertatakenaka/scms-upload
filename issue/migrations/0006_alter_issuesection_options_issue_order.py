# Generated by Django 5.0.3 on 2024-07-15 13:46

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("issue", "0005_issuesection_main_section_issuesection_translations_and_more"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="issuesection",
            options={"ordering": ["position"]},
        ),
        migrations.AddField(
            model_name="issue",
            name="order",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="This number controls the order issues appear for a specific year on the website grid",
                null=True,
            ),
        ),
    ]
