from django.db import migrations


def clean_series_markers(apps, schema_editor):
    HotWheelsModel = apps.get_model('catalog', 'HotWheelsModel')
    for model in HotWheelsModel.objects.filter(series__contains='New for 2022!'):
        model.series = ' '.join(model.series.replace('New for 2022!', ' ').split())
        model.save(update_fields=['series'])


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0003_dedupe_models_after_year_category'),
    ]

    operations = [
        migrations.RunPython(clean_series_markers, migrations.RunPython.noop),
    ]
