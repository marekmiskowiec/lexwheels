from django.db import migrations


def drop_legacy_sort_order(apps, schema_editor):
    table_name = 'collections_app_warehouselocation'
    with schema_editor.connection.cursor() as cursor:
        columns = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(cursor, table_name)
        }
    if 'sort_order' in columns:
        schema_editor.execute(f'ALTER TABLE {table_name} DROP COLUMN sort_order')


class Migration(migrations.Migration):

    dependencies = [
        ('collections_app', '0011_warehouse_location_grid_layout'),
    ]

    operations = [
        migrations.RunPython(drop_legacy_sort_order, migrations.RunPython.noop),
    ]
