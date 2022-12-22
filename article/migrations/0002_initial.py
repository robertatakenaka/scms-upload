# Generated by Django 3.2.12 on 2022-12-22 17:54

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('issue', '0001_initial'),
        ('article', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='article',
            name='issue',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='issue.issue'),
        ),
        migrations.AddField(
            model_name='article',
            name='related_items',
            field=models.ManyToManyField(related_name='related_to', through='article.RelatedItem', to='article.Article'),
        ),
        migrations.AddField(
            model_name='article',
            name='updated_by',
            field=models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='article_last_mod_user', to=settings.AUTH_USER_MODEL, verbose_name='Updater'),
        ),
    ]
