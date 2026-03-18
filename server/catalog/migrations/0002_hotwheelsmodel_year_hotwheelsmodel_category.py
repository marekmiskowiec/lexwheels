from django.db import migrations, models


def populate_year_and_category(apps, schema_editor):
    HotWheelsModel = apps.get_model('catalog', 'HotWheelsModel')
    HotWheelsModel.objects.filter(year__isnull=True).update(year=2022)
    HotWheelsModel.objects.filter(category='').update(category='Mainline')


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='hotwheelsmodel',
            name='category',
            field=models.CharField(blank=True, default='', max_length=64),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='hotwheelsmodel',
            name='year',
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.RunPython(populate_year_and_category, migrations.RunPython.noop),
    ]
