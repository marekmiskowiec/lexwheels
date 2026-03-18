from django.db import migrations


def clean_series_markers(apps, schema_editor):
    HotWheelsModel = apps.get_model('catalog', 'HotWheelsModel')
    markers = ('New for 2022!', 'New for 2023!')
    queryset = HotWheelsModel.objects.all()
    for model in queryset:
        updated = model.series or ''
        for marker in markers:
            updated = updated.replace(marker, ' ')
        cleaned = ' '.join(updated.split())
        if cleaned != model.series:
            model.series = cleaned
            model.save(update_fields=['series'])


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0006_hotwheelsmodel_packaging_photos'),
    ]

    operations = [
        migrations.RunPython(clean_series_markers, migrations.RunPython.noop),
    ]
