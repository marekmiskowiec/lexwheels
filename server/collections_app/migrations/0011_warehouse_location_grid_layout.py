from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('collections_app', '0010_remove_collectionitem_is_favorite'),
    ]

    operations = [
        migrations.AddField(
            model_name='warehouselocation',
            name='column_count',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='warehouselocation',
            name='row_count',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='warehouselocation',
            name='location_type',
            field=models.CharField(
                choices=[
                    ('box', 'Karton'),
                    ('wall', 'Ściana'),
                    ('shelf', 'Półka'),
                    ('display', 'Ekspozytor'),
                    ('other', 'Inne'),
                ],
                default='other',
                max_length=16,
            ),
        ),
    ]
