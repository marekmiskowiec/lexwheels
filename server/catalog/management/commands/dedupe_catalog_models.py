from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from catalog.models import HotWheelsModel
from collections_app.models import CollectionItem


class Command(BaseCommand):
    help = 'Deduplicate catalog models and safely merge collection references.'

    def add_arguments(self, parser):
        parser.add_argument('--brand', help='Limit dedupe to one brand.')
        parser.add_argument('--category', help='Limit dedupe to one category/line.')
        parser.add_argument('--year', type=int, help='Limit dedupe to one year.')
        parser.add_argument('--dry-run', action='store_true', help='Show what would be deduplicated without writing changes.')

    def handle(self, *args, **options):
        queryset = HotWheelsModel.objects.all().order_by('id')
        if options.get('brand'):
            queryset = queryset.filter(brand=options['brand'])
        if options.get('category'):
            queryset = queryset.filter(category=options['category'])
        if options.get('year'):
            queryset = queryset.filter(year=options['year'])

        groups = defaultdict(list)
        for model in queryset:
            groups[self.group_key(model)].append(model)

        duplicate_groups = [models for models in groups.values() if len(models) > 1]
        if options['dry_run']:
            self.stdout.write(f'Duplicate groups: {len(duplicate_groups)}')
            self.stdout.write(f'Extra rows: {sum(len(models) - 1 for models in duplicate_groups)}')
            return

        merged_items = 0
        deleted_models = 0
        with transaction.atomic():
            for models in duplicate_groups:
                canonical = self.choose_canonical(models)
                duplicates = [model for model in models if model.pk != canonical.pk]
                for duplicate in duplicates:
                    merged_items += self.reassign_collection_items(duplicate, canonical)
                    duplicate.delete()
                    deleted_models += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Deduplication complete. Groups: {len(duplicate_groups)}, deleted models: {deleted_models}, merged collection items: {merged_items}'
            )
        )

    @staticmethod
    def group_key(model: HotWheelsModel):
        return (
            model.brand,
            model.category,
            model.year,
            model.toy,
            model.number,
            model.model_name,
            model.series,
            model.series_number,
        )

    @staticmethod
    def choose_canonical(models: list[HotWheelsModel]) -> HotWheelsModel:
        def score(model: HotWheelsModel):
            return (
                1 if model.local_photo_path else 0,
                1 if model.short_card_local_photo_path else 0,
                1 if model.long_card_local_photo_path else 0,
                1 if model.loose_local_photo_path else 0,
                1 if model.photo_url else 0,
                1 if model.short_card_photo_url else 0,
                1 if model.long_card_photo_url else 0,
                1 if model.loose_photo_url else 0,
                -model.pk,
            )

        return max(models, key=score)

    @staticmethod
    def reassign_collection_items(source: HotWheelsModel, target: HotWheelsModel) -> int:
        merged_items = 0
        for item in CollectionItem.objects.filter(model=source):
            existing = CollectionItem.objects.filter(
                collection=item.collection,
                model=target,
                packaging_state=item.packaging_state,
                condition=item.condition,
            ).first()
            if existing:
                existing.quantity += item.quantity
                existing.is_favorite = existing.is_favorite or item.is_favorite
                existing.acquired_at = existing.acquired_at or item.acquired_at
                if item.notes:
                    existing.notes = '\n'.join(filter(None, [existing.notes, item.notes]))
                existing.save(update_fields=['quantity', 'is_favorite', 'acquired_at', 'notes'])
                item.delete()
            else:
                item.model = target
                item.save(update_fields=['model'])
            merged_items += 1
        return merged_items
