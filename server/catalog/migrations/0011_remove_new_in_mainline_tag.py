import hashlib
import re

from django.db import migrations


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
)
IGNORED_SERIES_MARKERS = ('New in Mainline',)
SERIES_FALLBACK_TAGS = {'From the Vault', 'Mail-In', 'Red Edition', 'ZAMAC'}


def normalize_marker(value: str, markers: tuple[tuple[str, str], ...]) -> str:
    raw = (value or '').strip()
    for marker, normalized in markers:
        if raw == marker or marker in raw:
            return normalized
    return raw


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

    for marker in IGNORED_SERIES_MARKERS:
        if marker in cleaned:
            cleaned = cleaned.replace(marker, ' ')

    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    if not cleaned and special_tag in SERIES_FALLBACK_TAGS:
        cleaned = special_tag

    return {
        'series': cleaned,
        'exclusive_store': exclusive_store,
        'special_tag': special_tag,
    }


def build_app_id(model, series: str, exclusive_store: str, special_tag: str) -> str:
    parts = [
        model.toy or '',
        model.number or '',
        model.model_name or '',
        series,
        exclusive_store,
        special_tag,
        model.series_number or '',
    ]
    return hashlib.sha256('|'.join(parts).encode('utf-8')).hexdigest()[:24]


def remove_new_in_mainline_tag(apps, schema_editor):
    HotWheelsModel = apps.get_model('catalog', 'HotWheelsModel')
    for model in HotWheelsModel.objects.all().order_by('pk'):
        parsed = parse_series_metadata(model.series or '')
        series = parsed['series']
        exclusive_store = parsed['exclusive_store'] or normalize_marker(model.exclusive_store or '', EXCLUSIVE_STORE_MARKERS)
        special_tag = ''
        if (model.special_tag or '').strip() != 'New in Mainline':
            special_tag = parsed['special_tag'] or normalize_marker(model.special_tag or '', SPECIAL_TAG_MARKERS)
        if series == 'New in Mainline':
            series = ''

        update_fields = []
        if (model.series or '') != series:
            model.series = series
            update_fields.append('series')
        if (getattr(model, 'exclusive_store', '') or '') != exclusive_store:
            model.exclusive_store = exclusive_store
            update_fields.append('exclusive_store')
        if (getattr(model, 'special_tag', '') or '') != special_tag:
            model.special_tag = special_tag
            update_fields.append('special_tag')

        new_app_id = build_app_id(model, series, exclusive_store, special_tag)
        if model.app_id != new_app_id:
            model.app_id = new_app_id
            update_fields.append('app_id')

        if update_fields:
            model.save(update_fields=update_fields)


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0010_normalize_series_metadata_fields'),
    ]

    operations = [
        migrations.RunPython(remove_new_in_mainline_tag, migrations.RunPython.noop),
    ]
