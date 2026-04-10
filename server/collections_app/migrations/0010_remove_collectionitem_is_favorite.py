from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('collections_app', '0009_storage_location_and_warehouse'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='collectionitem',
            name='is_favorite',
        ),
    ]
