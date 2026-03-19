from django.db import migrations


def clear_short_card_for_rlc_and_exclusives(apps, schema_editor):
    HotWheelsModel = apps.get_model('catalog', 'HotWheelsModel')
    (
        HotWheelsModel.objects.filter(category__iexact='RLC')
        .exclude(short_card_photo_url='', short_card_local_photo_path='')
        .update(short_card_photo_url='', short_card_local_photo_path='')
    )
    (
        HotWheelsModel.objects.exclude(exclusive_store='')
        .exclude(short_card_photo_url='', short_card_local_photo_path='')
        .update(short_card_photo_url='', short_card_local_photo_path='')
    )


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0011_remove_new_in_mainline_tag'),
    ]

    operations = [
        migrations.RunPython(clear_short_card_for_rlc_and_exclusives, migrations.RunPython.noop),
    ]
