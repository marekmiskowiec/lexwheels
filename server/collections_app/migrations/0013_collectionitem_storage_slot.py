from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('collections_app', '0012_drop_legacy_warehouse_sort_order'),
    ]

    operations = [
        migrations.AddField(
            model_name='collectionitem',
            name='storage_column',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='collectionitem',
            name='storage_row',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AlterUniqueTogether(
            name='collectionitem',
            unique_together={
                (
                    'collection',
                    'model',
                    'packaging_state',
                    'condition',
                    'is_sealed',
                    'has_soft_corners',
                    'has_protector',
                    'is_signed',
                    'has_bent_hook',
                    'has_cracked_blister',
                    'storage_location',
                    'storage_row',
                    'storage_column',
                )
            },
        ),
    ]
