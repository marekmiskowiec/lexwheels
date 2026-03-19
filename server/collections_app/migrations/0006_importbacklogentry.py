from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0012_clear_short_card_for_rlc_and_exclusives'),
        ('collections_app', '0005_collectionitem_card_damage_attributes'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ImportBacklogEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('open', 'Open'), ('resolved', 'Resolved'), ('ignored', 'Ignored')], default='open', max_length=16)),
                ('toy', models.CharField(blank=True, max_length=64)),
                ('model_name', models.CharField(max_length=255)),
                ('year', models.PositiveIntegerField(blank=True, null=True)),
                ('category', models.CharField(blank=True, max_length=64)),
                ('series', models.CharField(blank=True, max_length=255)),
                ('series_number', models.CharField(blank=True, max_length=32)),
                ('color', models.CharField(blank=True, max_length=128)),
                ('price', models.CharField(blank=True, max_length=128)),
                ('location', models.CharField(blank=True, max_length=255)),
                ('source_payload', models.JSONField(blank=True, default=dict)),
                ('import_count', models.PositiveIntegerField(default=1)),
                ('first_seen_at', models.DateTimeField(auto_now_add=True)),
                ('last_seen_at', models.DateTimeField(auto_now=True)),
                ('collection', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='import_backlog_entries', to='collections_app.collection')),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='import_backlog_entries', to=settings.AUTH_USER_MODEL)),
                ('resolved_model', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='resolved_import_backlog_entries', to='catalog.hotwheelsmodel')),
            ],
            options={
                'ordering': ('status', '-last_seen_at', 'model_name'),
            },
        ),
        migrations.AddConstraint(
            model_name='importbacklogentry',
            constraint=models.UniqueConstraint(fields=('owner', 'toy', 'model_name', 'year', 'category', 'series', 'series_number'), name='unique_import_backlog_entry_per_owner'),
        ),
    ]
