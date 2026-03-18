import hashlib
import json
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from catalog.models import HotWheelsModel


class Command(BaseCommand):
    help = 'Import Hot Wheels models from data/hot_wheels_data.json'
    SERIES_MARKERS = (
        'New for 2022!',
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--path',
            default=str(settings.PROJECT_ROOT / 'data' / 'hot_wheels_data.json'),
            help='Path to the JSON file to import.',
        )

    def handle(self, *args, **options):
        path = Path(options['path'])
        if not path.exists():
            raise CommandError(f'File not found: {path}')

        rows = json.loads(path.read_text())
        created = 0
        updated = 0

        for row in rows:
            app_id = self.build_app_id(row)
            defaults = {
                'toy': row.get('Toy', ''),
                'number': row.get('Number', ''),
                'model_name': row.get('Model Name', ''),
                'year': self.extract_year(row),
                'category': self.extract_category(row),
                'series': self.clean_series(row.get('Series', '')),
                'series_number': row.get('Series Number', ''),
                'photo_url': row.get('Photo', ''),
                'local_photo_path': row.get('Local Photo', ''),
            }
            _, was_created = HotWheelsModel.objects.update_or_create(app_id=app_id, defaults=defaults)
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(f'Import complete. Created: {created}, updated: {updated}'))

    @staticmethod
    def build_app_id(row: dict) -> str:
        parts = [
            row.get('Toy', ''),
            row.get('Number', ''),
            row.get('Model Name', ''),
            row.get('Series', ''),
            row.get('Series Number', ''),
        ]
        return hashlib.sha256('|'.join(parts).encode('utf-8')).hexdigest()[:24]

    @staticmethod
    def extract_year(row: dict) -> int | None:
        if row.get('Year'):
            try:
                return int(row['Year'])
            except (TypeError, ValueError):
                pass

        series = row.get('Series', '')
        match = re.search(r'(?:for|in)\s+(\d{4})', series)
        if match:
            return int(match.group(1))

        # Current repository dataset comes from the 2022 Hot Wheels page.
        return 2022

    @staticmethod
    def extract_category(row: dict) -> str:
        if row.get('Category'):
            return str(row['Category']).strip()
        return 'Mainline'

    @classmethod
    def clean_series(cls, value: str) -> str:
        cleaned = value or ''
        for marker in cls.SERIES_MARKERS:
            cleaned = cleaned.replace(marker, ' ')
        return re.sub(r'\s+', ' ', cleaned).strip()
