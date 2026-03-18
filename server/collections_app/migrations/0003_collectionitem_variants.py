from django.db import migrations, models


def migrate_packaging_states(apps, schema_editor):
    CollectionItem = apps.get_model('collections_app', 'CollectionItem')
    CollectionItem.objects.filter(packaging_state='carded').update(packaging_state='short_card')
    CollectionItem.objects.filter(packaging_state='damaged').update(packaging_state='short_card')


class Migration(migrations.Migration):

    dependencies = [
        ('collections_app', '0002_collection_kind'),
    ]

    operations = [
        migrations.RunPython(migrate_packaging_states, migrations.RunPython.noop),
        migrations.AlterModelOptions(
            name='collectionitem',
            options={
                'ordering': ('-is_favorite', 'model__number', 'model__model_name', 'packaging_state', 'condition'),
            },
        ),
        migrations.AlterField(
            model_name='collectionitem',
            name='packaging_state',
            field=models.CharField(
                choices=[
                    ('short_card', 'Krótka karta'),
                    ('long_card', 'Długa karta'),
                    ('loose', 'Luzak'),
                ],
                default='short_card',
                max_length=16,
            ),
        ),
        migrations.AlterUniqueTogether(
            name='collectionitem',
            unique_together={('collection', 'model', 'packaging_state', 'condition')},
        ),
    ]
