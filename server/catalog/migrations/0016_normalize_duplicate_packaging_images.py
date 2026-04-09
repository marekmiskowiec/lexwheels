from django.db import migrations


PACKAGING_FIELDS = (
    ('short_card_photo_url', 'short_card_local_photo_path'),
    ('long_card_photo_url', 'long_card_local_photo_path'),
    ('loose_photo_url', 'loose_local_photo_path'),
)


def image_signature(local_path: str, url: str) -> tuple[str, str]:
    local_path = (local_path or '').strip()
    url = (url or '').strip()
    if local_path:
        return ('local', local_path)
    if url:
        return ('url', url)
    return ('', '')


def normalize_duplicate_packaging_images(apps, schema_editor):
    HotWheelsModel = apps.get_model('catalog', 'HotWheelsModel')

    fields_to_load = [
        'id',
        'photo_url',
        'local_photo_path',
        'short_card_photo_url',
        'short_card_local_photo_path',
        'long_card_photo_url',
        'long_card_local_photo_path',
        'loose_photo_url',
        'loose_local_photo_path',
    ]

    for model in HotWheelsModel.objects.all().only(*fields_to_load):
        packaging_refs = []
        for url_field, path_field in PACKAGING_FIELDS:
            local_path = getattr(model, path_field, '')
            url = getattr(model, url_field, '')
            signature = image_signature(local_path, url)
            if signature != ('', ''):
                packaging_refs.append((signature, url_field, path_field, url, local_path))

        if len(packaging_refs) < 2:
            continue

        signatures = {signature for signature, *_ in packaging_refs}
        if len(signatures) != 1:
            continue

        duplicate_signature = next(iter(signatures))
        generic_signature = image_signature(model.local_photo_path, model.photo_url)
        if generic_signature not in {('', ''), duplicate_signature}:
            continue

        _, _, _, representative_url, representative_local_path = packaging_refs[0]
        update_fields = []

        if generic_signature == ('', ''):
            model.photo_url = representative_url
            model.local_photo_path = representative_local_path
            update_fields.extend(['photo_url', 'local_photo_path'])

        for _, url_field, path_field, _, _ in packaging_refs:
            if getattr(model, url_field, ''):
                setattr(model, url_field, '')
                update_fields.append(url_field)
            if getattr(model, path_field, ''):
                setattr(model, path_field, '')
                update_fields.append(path_field)

        if update_fields:
            model.save(update_fields=sorted(set(update_fields)))


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0015_clean_extended_model_color_suffixes'),
    ]

    operations = [
        migrations.RunPython(normalize_duplicate_packaging_images, migrations.RunPython.noop),
    ]
