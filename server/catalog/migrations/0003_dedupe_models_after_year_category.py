import hashlib

from django.db import migrations


def legacy_app_id(model) -> str:
    parts = [
        model.toy or '',
        model.number or '',
        model.model_name or '',
        model.series or '',
        model.series_number or '',
    ]
    return hashlib.sha256('|'.join(parts).encode('utf-8')).hexdigest()[:24]


def dedupe_models(apps, schema_editor):
    HotWheelsModel = apps.get_model('catalog', 'HotWheelsModel')
    CollectionItem = apps.get_model('collections_app', 'CollectionItem')

    grouped = {}
    for model in HotWheelsModel.objects.all().order_by('id'):
        key = (model.toy, model.number, model.model_name, model.series, model.series_number)
        grouped.setdefault(key, []).append(model)

    for models in grouped.values():
        keeper = models[0]
        duplicates = models[1:]
        desired_app_id = legacy_app_id(keeper)

        if duplicates:
            for duplicate in duplicates:
                for item in CollectionItem.objects.filter(model_id=duplicate.id):
                    exists = CollectionItem.objects.filter(
                        collection_id=item.collection_id,
                        model_id=keeper.id,
                    ).exists()
                    if exists:
                        item.delete()
                    else:
                        item.model_id = keeper.id
                        item.save(update_fields=['model'])
                duplicate.delete()

        keeper.app_id = desired_app_id
        keeper.save(update_fields=['app_id'])


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0002_hotwheelsmodel_year_hotwheelsmodel_category'),
        ('collections_app', '0002_collection_kind'),
    ]

    operations = [
        migrations.RunPython(dedupe_models, migrations.RunPython.noop),
    ]
