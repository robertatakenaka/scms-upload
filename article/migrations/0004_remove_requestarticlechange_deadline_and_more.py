# Generated by Django 5.0.3 on 2024-08-19 20:18

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("article", "0003_article_sections_articletitle_language_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="requestarticlechange",
            name="deadline",
        ),
        migrations.RemoveField(
            model_name="requestarticlechange",
            name="demanded_user",
        ),
        migrations.RemoveField(
            model_name="requestarticlechange",
            name="pid_v3",
        ),
    ]
