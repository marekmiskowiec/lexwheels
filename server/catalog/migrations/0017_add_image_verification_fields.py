from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('catalog', '0016_normalize_duplicate_packaging_images'),
    ]

    operations = [
        migrations.AddField(
            model_name='hotwheelsmodel',
            name='images_verified_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='hotwheelsmodel',
            name='images_verified_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='verified_catalog_models',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
