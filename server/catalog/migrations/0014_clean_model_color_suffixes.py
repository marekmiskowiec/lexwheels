import re

from django.db import migrations


COLOR_VARIANT_SUFFIX_PATTERN = re.compile(r'\s*\((?:\d+(?:st|nd|rd|th)\s+color)\)\s*$', re.IGNORECASE)


def clean_model_color_suffixes(apps, schema_editor):
    HotWheelsModel = apps.get_model('catalog', 'HotWheelsModel')

    for model in HotWheelsModel.objects.all().only('id', 'model_name'):
        cleaned_name = re.sub(r'\s+', ' ', COLOR_VARIANT_SUFFIX_PATTERN.sub('', model.model_name or '')).strip()
        if cleaned_name and cleaned_name != model.model_name:
            model.model_name = cleaned_name
            model.save(update_fields=['model_name'])


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0013_hotwheelsmodel_case_codes'),
    ]

    operations = [
        migrations.RunPython(clean_model_color_suffixes, migrations.RunPython.noop),
    ]
