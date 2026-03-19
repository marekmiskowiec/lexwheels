import hashlib
import re

from django.db import migrations


SERIES_MARKER_PATTERN = re.compile(r'New for 20\d{2}!')


def clean_series(value: str) -> str:
    cleaned = SERIES_MARKER_PATTERN.sub(' ', value or '')
    return re.sub(r'\s+', ' ', cleaned).strip()


def build_app_id(model) -> str:
    parts = [
        model.toy or '',
        model.number or '',
        model.model_name or '',
        clean_series(model.series or ''),
        model.series_number or '',
    ]
    return hashlib.sha256('|'.join(parts).encode('utf-8')).hexdigest()[:24]


def clean_series_markers_and_rebuild_ids(apps, schema_editor):
    HotWheelsModel = apps.get_model('catalog', 'HotWheelsModel')
    queryset = HotWheelsModel.objects.all().order_by('pk')
    for model in queryset:
        cleaned_series = clean_series(model.series or '')
        new_app_id = build_app_id(model)
        update_fields = []
        if cleaned_series != (model.series or ''):
            model.series = cleaned_series
            update_fields.append('series')
        if new_app_id != model.app_id:
            model.app_id = new_app_id
            update_fields.append('app_id')
        if update_fields:
            model.save(update_fields=update_fields)


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0007_clean_new_for_2023_from_series'),
    ]

    operations = [
        migrations.RunPython(clean_series_markers_and_rebuild_ids, migrations.RunPython.noop),
    ]
