from django.db import migrations, models


def populate_brand(apps, schema_editor):
    HotWheelsModel = apps.get_model('catalog', 'HotWheelsModel')
    HotWheelsModel.objects.filter(brand='').update(brand='Hot Wheels')


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0004_clean_new_for_2022_from_series'),
    ]

    operations = [
        migrations.AddField(
            model_name='hotwheelsmodel',
            name='brand',
            field=models.CharField(default='Hot Wheels', max_length=64),
        ),
        migrations.RunPython(populate_brand, migrations.RunPython.noop),
    ]
