from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def copy_entries_to_reports(apps, schema_editor):
    ImportBacklogEntry = apps.get_model('collections_app', 'ImportBacklogEntry')
    ImportBacklogReport = apps.get_model('collections_app', 'ImportBacklogReport')

    grouped = {}
    duplicates_to_delete = []
    for entry in ImportBacklogEntry.objects.all().order_by('id'):
        key = (
            entry.toy or '',
            entry.model_name,
            entry.year,
            entry.category or '',
            entry.series or '',
            entry.series_number or '',
        )
        global_entry = grouped.get(key)
        if global_entry is None:
            global_entry = entry
            global_entry.report_count = 0
            global_entry.save(update_fields=['report_count'])
            grouped[key] = global_entry
        else:
            duplicates_to_delete.append(entry.pk)

        ImportBacklogReport.objects.create(
            backlog_entry=global_entry,
            owner_id=entry.owner_id,
            collection_id=entry.collection_id,
            color=entry.color,
            price=entry.price,
            location=entry.location,
            source_payload=entry.source_payload,
            import_count=entry.import_count,
            first_seen_at=entry.first_seen_at,
            last_seen_at=entry.last_seen_at,
        )
        global_entry.report_count += 1
        if entry.first_seen_at < global_entry.first_seen_at:
            global_entry.first_seen_at = entry.first_seen_at
        if entry.last_seen_at > global_entry.last_seen_at:
            global_entry.last_seen_at = entry.last_seen_at
        global_entry.save(update_fields=['report_count', 'first_seen_at', 'last_seen_at'])

    if duplicates_to_delete:
        ImportBacklogEntry.objects.filter(pk__in=duplicates_to_delete).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('collections_app', '0006_importbacklogentry'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ImportBacklogReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('color', models.CharField(blank=True, max_length=128)),
                ('price', models.CharField(blank=True, max_length=128)),
                ('location', models.CharField(blank=True, max_length=255)),
                ('source_payload', models.JSONField(blank=True, default=dict)),
                ('import_count', models.PositiveIntegerField(default=1)),
                ('first_seen_at', models.DateTimeField(auto_now_add=True)),
                ('last_seen_at', models.DateTimeField(auto_now=True)),
                ('backlog_entry', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reports', to='collections_app.importbacklogentry')),
                ('collection', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='import_backlog_reports', to='collections_app.collection')),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='import_backlog_reports', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('-last_seen_at',),
            },
        ),
        migrations.AddField(
            model_name='importbacklogentry',
            name='report_count',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.RunPython(copy_entries_to_reports, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name='importbacklogentry',
            name='unique_import_backlog_entry_per_owner',
        ),
        migrations.RemoveField(
            model_name='importbacklogentry',
            name='owner',
        ),
        migrations.RemoveField(
            model_name='importbacklogentry',
            name='collection',
        ),
        migrations.RemoveField(
            model_name='importbacklogentry',
            name='color',
        ),
        migrations.RemoveField(
            model_name='importbacklogentry',
            name='price',
        ),
        migrations.RemoveField(
            model_name='importbacklogentry',
            name='location',
        ),
        migrations.RemoveField(
            model_name='importbacklogentry',
            name='source_payload',
        ),
        migrations.RemoveField(
            model_name='importbacklogentry',
            name='import_count',
        ),
        migrations.AddConstraint(
            model_name='importbacklogentry',
            constraint=models.UniqueConstraint(fields=('toy', 'model_name', 'year', 'category', 'series', 'series_number'), name='unique_global_import_backlog_entry'),
        ),
        migrations.AddConstraint(
            model_name='importbacklogreport',
            constraint=models.UniqueConstraint(fields=('backlog_entry', 'owner', 'collection', 'color'), name='unique_import_backlog_report_per_context'),
        ),
    ]
