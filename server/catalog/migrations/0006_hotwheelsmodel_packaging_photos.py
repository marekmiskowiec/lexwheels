from django.db import migrations, models


def backfill_packaging_photos(apps, schema_editor):
    HotWheelsModel = apps.get_model('catalog', 'HotWheelsModel')
    for model in HotWheelsModel.objects.all():
        model.short_card_photo_url = model.short_card_photo_url or model.photo_url
        model.short_card_local_photo_path = model.short_card_local_photo_path or model.local_photo_path
        model.long_card_photo_url = model.long_card_photo_url or model.photo_url
        model.long_card_local_photo_path = model.long_card_local_photo_path or model.local_photo_path
        model.loose_photo_url = model.loose_photo_url or model.photo_url
        model.loose_local_photo_path = model.loose_local_photo_path or model.local_photo_path
        model.save(
            update_fields=[
                'short_card_photo_url',
                'short_card_local_photo_path',
                'long_card_photo_url',
                'long_card_local_photo_path',
                'loose_photo_url',
                'loose_local_photo_path',
            ]
        )


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0005_hotwheelsmodel_brand'),
    ]

    operations = [
        migrations.AddField(
            model_name='hotwheelsmodel',
            name='short_card_photo_url',
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name='hotwheelsmodel',
            name='short_card_local_photo_path',
            field=models.CharField(blank=True, max_length=512),
        ),
        migrations.AddField(
            model_name='hotwheelsmodel',
            name='long_card_photo_url',
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name='hotwheelsmodel',
            name='long_card_local_photo_path',
            field=models.CharField(blank=True, max_length=512),
        ),
        migrations.AddField(
            model_name='hotwheelsmodel',
            name='loose_photo_url',
            field=models.URLField(blank=True),
        ),
        migrations.AddField(
            model_name='hotwheelsmodel',
            name='loose_local_photo_path',
            field=models.CharField(blank=True, max_length=512),
        ),
        migrations.RunPython(backfill_packaging_photos, migrations.RunPython.noop),
    ]
