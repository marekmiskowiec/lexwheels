import hashlib
import re

from django.db import migrations, models


SERIES_MARKER_PATTERN = re.compile(r'New for 20\d{2}!')
EXCLUSIVE_STORE_MARKERS = (
    ('Dollar Tree/Family Dollar Exclusive', 'Dollar Tree/Family Dollar Exclusive'),
    ('Family Dollar/Dollar Tree Exclusive', 'Dollar Tree/Family Dollar Exclusive'),
    ('Dollar General Exclusive', 'Dollar General Exclusive'),
    ('GameStop Exclusive', 'GameStop Exclusive'),
    ('Kroger Exclusive', 'Kroger Exclusive'),
    ('Target Exclusive', 'Target Exclusive'),
    ('Walmart Exclusive', 'Walmart Exclusive'),
    ('Best Buy Exclusive', 'Best Buy Exclusive'),
    ('Walgreens Exclusive', 'Walgreens Exclusive'),
    ('WalgreensExclusive', 'Walgreens Exclusive'),
)
SPECIAL_TAG_MARKERS = (
    ('"From the Vault" Exclusive', 'From the Vault'),
    ('Super Treasure Hunt', 'Super Treasure Hunt'),
    ('Treasure Hunt', 'Treasure Hunt'),
    ('Red Edition', 'Red Edition'),
    ('ZAMAC', 'ZAMAC'),
    ('Mail-In', 'Mail-In'),
    ('Mail In', 'Mail-In'),
    ('New in Mainline', 'New in Mainline'),
)


def parse_series_metadata(value: str) -> dict[str, str]:
    raw = value or ''
    cleaned = SERIES_MARKER_PATTERN.sub(' ', raw)

    exclusive_store = ''
    for marker, normalized in EXCLUSIVE_STORE_MARKERS:
        if marker in cleaned:
            cleaned = cleaned.replace(marker, ' ')
            exclusive_store = normalized
            break

    special_tag = ''
    for marker, normalized in SPECIAL_TAG_MARKERS:
        if marker in cleaned:
            cleaned = cleaned.replace(marker, ' ')
            special_tag = normalized
            break

    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    if not cleaned and special_tag in {'From the Vault', 'Mail-In', 'New in Mainline', 'Red Edition', 'ZAMAC'}:
        cleaned = special_tag

    return {
        'series': cleaned,
        'exclusive_store': exclusive_store,
        'special_tag': special_tag,
    }


def build_app_id(model, parsed: dict[str, str]) -> str:
    parts = [
        model.toy or '',
        model.number or '',
        model.model_name or '',
        parsed['series'],
        parsed['exclusive_store'],
        parsed['special_tag'],
        model.series_number or '',
    ]
    return hashlib.sha256('|'.join(parts).encode('utf-8')).hexdigest()[:24]


def extract_series_metadata(apps, schema_editor):
    HotWheelsModel = apps.get_model('catalog', 'HotWheelsModel')
    for model in HotWheelsModel.objects.all().order_by('pk'):
        parsed = parse_series_metadata(model.series or '')
        update_fields = []
        if (model.series or '') != parsed['series']:
            model.series = parsed['series']
            update_fields.append('series')
        if (getattr(model, 'exclusive_store', '') or '') != parsed['exclusive_store']:
            model.exclusive_store = parsed['exclusive_store']
            update_fields.append('exclusive_store')
        if (getattr(model, 'special_tag', '') or '') != parsed['special_tag']:
            model.special_tag = parsed['special_tag']
            update_fields.append('special_tag')
        new_app_id = build_app_id(model, parsed)
        if model.app_id != new_app_id:
            model.app_id = new_app_id
            update_fields.append('app_id')
        if update_fields:
            model.save(update_fields=update_fields)


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0008_clean_new_for_markers_and_rebuild_app_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='hotwheelsmodel',
            name='exclusive_store',
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.AddField(
            model_name='hotwheelsmodel',
            name='special_tag',
            field=models.CharField(blank=True, max_length=128),
        ),
        migrations.RunPython(extract_series_metadata, migrations.RunPython.noop),
    ]
