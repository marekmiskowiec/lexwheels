from django.db import migrations, models


def normalize_warehouse_locations(apps, schema_editor):
    WarehouseLocation = apps.get_model('collections_app', 'WarehouseLocation')

    WarehouseLocation.objects.filter(location_type='display').update(
        row_count=3,
        column_count=8,
        is_marked_full=False,
    )
    WarehouseLocation.objects.exclude(location_type='display').update(
        row_count=None,
        column_count=None,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('collections_app', '0013_collectionitem_storage_slot'),
    ]

    operations = [
        migrations.AddField(
            model_name='warehouselocation',
            name='is_marked_full',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='warehouselocation',
            name='location_type',
            field=models.CharField(
                choices=[
                    ('box', 'Karton'),
                    ('hw_box', 'Karton Hot Wheels'),
                    ('wall', 'Ściana'),
                    ('shelf', 'Półka'),
                    ('display', 'Ekspozytor'),
                    ('other', 'Inne'),
                ],
                default='other',
                max_length=16,
            ),
        ),
        migrations.RunPython(normalize_warehouse_locations, migrations.RunPython.noop),
    ]
