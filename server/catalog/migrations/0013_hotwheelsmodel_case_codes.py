from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0012_clear_short_card_for_rlc_and_exclusives'),
    ]

    operations = [
        migrations.AddField(
            model_name='hotwheelsmodel',
            name='case_codes',
            field=models.CharField(blank=True, max_length=64),
        ),
    ]
