from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def migrate_wishlist_items_to_wanted(apps, schema_editor):
    Collection = apps.get_model('collections_app', 'Collection')
    CollectionItem = apps.get_model('collections_app', 'CollectionItem')
    WantedItem = apps.get_model('collections_app', 'WantedItem')

    for collection in Collection.objects.filter(kind='wishlist').iterator():
        item_queryset = CollectionItem.objects.filter(collection_id=collection.pk).order_by('pk')
        for item in item_queryset:
            wanted_item, created = WantedItem.objects.get_or_create(
                owner_id=collection.owner_id,
                model_id=item.model_id,
                packaging_state=item.packaging_state,
                condition_min=item.condition,
                defaults={
                    'notes': item.notes,
                    'is_active': True,
                },
            )
            if created:
                continue

            incoming_note = (item.notes or '').strip()
            existing_note = (wanted_item.notes or '').strip()
            if incoming_note and incoming_note not in existing_note:
                wanted_item.notes = '\n\n'.join(filter(None, [existing_note, incoming_note]))
                wanted_item.save(update_fields=['notes', 'updated_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0012_clear_short_card_for_rlc_and_exclusives'),
        ('collections_app', '0007_globalize_import_backlog'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='WantedItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('packaging_state', models.CharField(choices=[('any', 'Dowolne opakowanie'), ('short_card', 'Krótka karta'), ('long_card', 'Długa karta'), ('loose', 'Luzak')], default='any', max_length=16)),
                ('condition_min', models.CharField(choices=[('mint', 'Mint'), ('good', 'Good'), ('used', 'Used')], default='good', max_length=16)),
                ('budget_max', models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True)),
                ('notes', models.TextField(blank=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('model', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='wanted_items', to='catalog.hotwheelsmodel')),
                ('owner', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='wanted_items', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('-is_active', '-updated_at', '-created_at'),
            },
        ),
        migrations.AddConstraint(
            model_name='wanteditem',
            constraint=models.UniqueConstraint(fields=('owner', 'model', 'packaging_state', 'condition_min'), name='unique_wanted_item_per_owner_variant'),
        ),
        migrations.RunPython(migrate_wishlist_items_to_wanted, migrations.RunPython.noop),
    ]
