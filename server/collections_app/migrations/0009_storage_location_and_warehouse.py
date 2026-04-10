from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('collections_app', '0008_wanteditem'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='collectionitem',
            name='storage_location',
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.CreateModel(
            name='WarehouseLocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120)),
                ('location_type', models.CharField(choices=[('box', 'Karton'), ('wall', 'Ściana'), ('shelf', 'Półka'), ('other', 'Inne')], default='other', max_length=16)),
                ('description', models.TextField(blank=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='warehouse_locations', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('name',),
                'unique_together': {('owner', 'name')},
            },
        ),
    ]
