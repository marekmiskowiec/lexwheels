from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('collections_app', '0003_collectionitem_variants'),
    ]

    operations = [
        migrations.AddField(
            model_name='collectionitem',
            name='has_protector',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='collectionitem',
            name='has_soft_corners',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='collectionitem',
            name='is_sealed',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='collectionitem',
            name='is_signed',
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
                ),
            },
        ),
    ]
