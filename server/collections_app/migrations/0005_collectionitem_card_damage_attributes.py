from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('collections_app', '0004_collectionitem_packaging_attributes'),
    ]

    operations = [
        migrations.AddField(
            model_name='collectionitem',
            name='has_bent_hook',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='collectionitem',
            name='has_cracked_blister',
            field=models.BooleanField(default=False),
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
                ),
            },
        ),
    ]
