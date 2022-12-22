# Generated by Django 3.2.12 on 2022-12-22 17:54

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('issue', '0001_initial'),
        ('journal', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('collection', '0001_initial'),
        ('article', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='scielojournal',
            name='official_journal',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='journal.officialjournal'),
        ),
        migrations.AddField(
            model_name='scielojournal',
            name='updated_by',
            field=models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='scielojournal_last_mod_user', to=settings.AUTH_USER_MODEL, verbose_name='Updater'),
        ),
        migrations.AddField(
            model_name='scieloissue',
            name='creator',
            field=models.ForeignKey(editable=False, on_delete=django.db.models.deletion.CASCADE, related_name='scieloissue_creator', to=settings.AUTH_USER_MODEL, verbose_name='Creator'),
        ),
        migrations.AddField(
            model_name='scieloissue',
            name='official_issue',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='issue.issue'),
        ),
        migrations.AddField(
            model_name='scieloissue',
            name='scielo_journal',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='collection.scielojournal'),
        ),
        migrations.AddField(
            model_name='scieloissue',
            name='updated_by',
            field=models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='scieloissue_last_mod_user', to=settings.AUTH_USER_MODEL, verbose_name='Updater'),
        ),
        migrations.AddField(
            model_name='scielofile',
            name='scielo_issue',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='collection.scieloissue'),
        ),
        migrations.AddField(
            model_name='scielodocument',
            name='creator',
            field=models.ForeignKey(editable=False, on_delete=django.db.models.deletion.CASCADE, related_name='scielodocument_creator', to=settings.AUTH_USER_MODEL, verbose_name='Creator'),
        ),
        migrations.AddField(
            model_name='scielodocument',
            name='official_document',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='article.article'),
        ),
        migrations.AddField(
            model_name='scielodocument',
            name='scielo_issue',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='collection.scieloissue'),
        ),
        migrations.AddField(
            model_name='scielodocument',
            name='updated_by',
            field=models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='scielodocument_last_mod_user', to=settings.AUTH_USER_MODEL, verbose_name='Updater'),
        ),
        migrations.AddField(
            model_name='newwebsiteconfiguration',
            name='creator',
            field=models.ForeignKey(editable=False, on_delete=django.db.models.deletion.CASCADE, related_name='newwebsiteconfiguration_creator', to=settings.AUTH_USER_MODEL, verbose_name='Creator'),
        ),
        migrations.AddField(
            model_name='newwebsiteconfiguration',
            name='updated_by',
            field=models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='newwebsiteconfiguration_last_mod_user', to=settings.AUTH_USER_MODEL, verbose_name='Updater'),
        ),
        migrations.AddField(
            model_name='filesstorageconfiguration',
            name='creator',
            field=models.ForeignKey(editable=False, on_delete=django.db.models.deletion.CASCADE, related_name='filesstorageconfiguration_creator', to=settings.AUTH_USER_MODEL, verbose_name='Creator'),
        ),
        migrations.AddField(
            model_name='filesstorageconfiguration',
            name='updated_by',
            field=models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='filesstorageconfiguration_last_mod_user', to=settings.AUTH_USER_MODEL, verbose_name='Updater'),
        ),
        migrations.AddField(
            model_name='collection',
            name='creator',
            field=models.ForeignKey(editable=False, on_delete=django.db.models.deletion.CASCADE, related_name='collection_creator', to=settings.AUTH_USER_MODEL, verbose_name='Creator'),
        ),
        migrations.AddField(
            model_name='collection',
            name='updated_by',
            field=models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='collection_last_mod_user', to=settings.AUTH_USER_MODEL, verbose_name='Updater'),
        ),
        migrations.AddField(
            model_name='classicwebsiteconfiguration',
            name='collection',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='collection.collection'),
        ),
        migrations.AddField(
            model_name='classicwebsiteconfiguration',
            name='creator',
            field=models.ForeignKey(editable=False, on_delete=django.db.models.deletion.CASCADE, related_name='classicwebsiteconfiguration_creator', to=settings.AUTH_USER_MODEL, verbose_name='Creator'),
        ),
        migrations.AddField(
            model_name='classicwebsiteconfiguration',
            name='updated_by',
            field=models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='classicwebsiteconfiguration_last_mod_user', to=settings.AUTH_USER_MODEL, verbose_name='Updater'),
        ),
        migrations.CreateModel(
            name='SciELOHTMLFile',
            fields=[
                ('filewithlang_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='collection.filewithlang')),
                ('part', models.CharField(max_length=6, verbose_name='Part')),
            ],
            bases=('collection.filewithlang',),
        ),
        migrations.CreateModel(
            name='XMLFile',
            fields=[
                ('filewithlang_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='collection.filewithlang')),
                ('languages', models.JSONField(null=True)),
                ('public_uri', models.URLField(max_length=255, null=True, verbose_name='Public URI')),
                ('public_object_name', models.CharField(max_length=255, null=True, verbose_name='Public object name')),
            ],
            bases=('collection.filewithlang',),
        ),
        migrations.AddIndex(
            model_name='scielojournal',
            index=models.Index(fields=['acron'], name='collection__acron_fd9a83_idx'),
        ),
        migrations.AddIndex(
            model_name='scielojournal',
            index=models.Index(fields=['collection'], name='collection__collect_9538b6_idx'),
        ),
        migrations.AddIndex(
            model_name='scielojournal',
            index=models.Index(fields=['scielo_issn'], name='collection__scielo__dac95a_idx'),
        ),
        migrations.AddIndex(
            model_name='scielojournal',
            index=models.Index(fields=['availability_status'], name='collection__availab_c5b518_idx'),
        ),
        migrations.AddIndex(
            model_name='scielojournal',
            index=models.Index(fields=['official_journal'], name='collection__officia_6d9e77_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='scielojournal',
            unique_together={('collection', 'acron'), ('collection', 'scielo_issn')},
        ),
        migrations.AddIndex(
            model_name='scieloissue',
            index=models.Index(fields=['scielo_journal'], name='collection__scielo__caa1e6_idx'),
        ),
        migrations.AddIndex(
            model_name='scieloissue',
            index=models.Index(fields=['issue_pid'], name='collection__issue_p_b24fd5_idx'),
        ),
        migrations.AddIndex(
            model_name='scieloissue',
            index=models.Index(fields=['issue_folder'], name='collection__issue_f_e45b9f_idx'),
        ),
        migrations.AddIndex(
            model_name='scieloissue',
            index=models.Index(fields=['official_issue'], name='collection__officia_bd2f58_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='scieloissue',
            unique_together={('scielo_journal', 'issue_pid'), ('issue_pid', 'issue_folder'), ('scielo_journal', 'issue_folder')},
        ),
        migrations.AddIndex(
            model_name='scielofile',
            index=models.Index(fields=['file_id'], name='collection__file_id_770a89_idx'),
        ),
        migrations.AddIndex(
            model_name='scielofile',
            index=models.Index(fields=['relative_path'], name='collection__relativ_6cd669_idx'),
        ),
        migrations.AddIndex(
            model_name='scielofile',
            index=models.Index(fields=['name'], name='collection__name_dd19c6_idx'),
        ),
        migrations.AddIndex(
            model_name='scielofile',
            index=models.Index(fields=['object_name'], name='collection__object__dd3e6a_idx'),
        ),
        migrations.AddIndex(
            model_name='scielofile',
            index=models.Index(fields=['scielo_issue'], name='collection__scielo__995583_idx'),
        ),
        migrations.AddField(
            model_name='scielodocument',
            name='renditions_files',
            field=models.ManyToManyField(null=True, related_name='renditions_files', to='collection.FileWithLang'),
        ),
        migrations.AddIndex(
            model_name='newwebsiteconfiguration',
            index=models.Index(fields=['url'], name='collection__url_aaa55d_idx'),
        ),
        migrations.AddIndex(
            model_name='filewithlang',
            index=models.Index(fields=['lang'], name='collection__lang_4177e6_idx'),
        ),
        migrations.AddIndex(
            model_name='filesstorageconfiguration',
            index=models.Index(fields=['host'], name='collection__host_831dfb_idx'),
        ),
        migrations.AddIndex(
            model_name='filesstorageconfiguration',
            index=models.Index(fields=['bucket_root'], name='collection__bucket__65c090_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='filesstorageconfiguration',
            unique_together={('host', 'bucket_root')},
        ),
        migrations.AddIndex(
            model_name='classicwebsiteconfiguration',
            index=models.Index(fields=['collection'], name='collection__collect_565bb2_idx'),
        ),
        migrations.AddIndex(
            model_name='assetfile',
            index=models.Index(fields=['is_supplementary_material'], name='collection__is_supp_106058_idx'),
        ),
        migrations.AddField(
            model_name='xmlfile',
            name='assets_files',
            field=models.ManyToManyField(to='collection.AssetFile'),
        ),
        migrations.AddField(
            model_name='scielohtmlfile',
            name='assets_files',
            field=models.ManyToManyField(to='collection.AssetFile'),
        ),
        migrations.AddField(
            model_name='scielodocument',
            name='html_files',
            field=models.ManyToManyField(null=True, related_name='html_files', to='collection.SciELOHTMLFile'),
        ),
        migrations.AddField(
            model_name='scielodocument',
            name='xml_files',
            field=models.ManyToManyField(null=True, related_name='xml_files', to='collection.XMLFile'),
        ),
        migrations.AddIndex(
            model_name='scielohtmlfile',
            index=models.Index(fields=['part'], name='collection__part_d49aa5_idx'),
        ),
        migrations.AddIndex(
            model_name='scielodocument',
            index=models.Index(fields=['scielo_issue'], name='collection__scielo__5bef2c_idx'),
        ),
        migrations.AddIndex(
            model_name='scielodocument',
            index=models.Index(fields=['pid'], name='collection__pid_837f75_idx'),
        ),
        migrations.AddIndex(
            model_name='scielodocument',
            index=models.Index(fields=['file_id'], name='collection__file_id_a2e87a_idx'),
        ),
        migrations.AddIndex(
            model_name='scielodocument',
            index=models.Index(fields=['official_document'], name='collection__officia_9656d6_idx'),
        ),
        migrations.AlterUniqueTogether(
            name='scielodocument',
            unique_together={('scielo_issue', 'file_id'), ('pid', 'file_id'), ('scielo_issue', 'pid')},
        ),
    ]
