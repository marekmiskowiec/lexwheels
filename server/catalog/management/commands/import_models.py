import hashlib
import json
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from catalog.models import HotWheelsModel


class Command(BaseCommand):
    help = 'Import catalog models from one JSON file or from the full data/catalog tree.'
    SERIES_MARKERS = (
        'New for 2022!',
        'New for 2023!',
    )
    DEFAULT_DATASET_PATH = settings.PROJECT_ROOT / 'data' / 'catalog' / 'hot-wheels' / 'mainline' / '2022.json'
    DEFAULT_DATASET_ROOT = settings.PROJECT_ROOT / 'data' / 'catalog'

    def add_arguments(self, parser):
        parser.add_argument(
            '--path',
            help='Path to one JSON file to import.',
        )
        parser.add_argument(
            '--root',
            default=str(self.DEFAULT_DATASET_ROOT),
            help='Root directory for bulk import from data/catalog.',
        )
        parser.add_argument(
            '--brand',
            help='Import only datasets for one brand slug, for example "hot-wheels" or "matchbox".',
        )
        parser.add_argument(
            '--line',
            help='Import only datasets for one line slug, for example "mainline", "premium" or "rlc".',
        )
        parser.add_argument(
            '--year',
            type=int,
            help='Import only datasets for one year.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show which files would be imported without writing to the database.',
        )

    def handle(self, *args, **options):
        dataset_files = self.resolve_dataset_files(options)
        if options['dry_run']:
            self.stdout.write(f'Found {len(dataset_files)} dataset file(s):')
            for path in dataset_files:
                self.stdout.write(f'- {path}')
            return

        created = 0
        updated = 0
        imported_files = 0

        for path in dataset_files:
            rows = self.load_rows(path)
            imported_files += 1
            metadata = self.extract_metadata_from_path(path)

            for row in rows:
                app_id = self.build_app_id(row)
                local_photo = self.clean_optional_text(row.get('Local Photo'))
                photo_url = self.clean_optional_text(row.get('Photo'))
                short_card_photo_url = self.clean_optional_text(row.get('Short Card Photo')) or photo_url
                long_card_photo_url = self.clean_optional_text(row.get('Long Card Photo')) or photo_url
                loose_photo_url = self.clean_optional_text(row.get('Loose Photo')) or photo_url
                short_card_local_photo = self.clean_optional_text(row.get('Short Card Local Photo')) or local_photo
                long_card_local_photo = self.clean_optional_text(row.get('Long Card Local Photo')) or local_photo
                loose_local_photo = self.clean_optional_text(row.get('Loose Local Photo')) or local_photo
                defaults = {
                    'brand': self.extract_brand(row, metadata),
                    'toy': row.get('Toy', ''),
                    'number': row.get('Number', ''),
                    'model_name': row.get('Model Name', ''),
                    'year': self.extract_year(row, metadata),
                    'category': self.extract_category(row, metadata),
                    'series': self.clean_series(row.get('Series', '')),
                    'series_number': row.get('Series Number', ''),
                    'photo_url': photo_url,
                    'local_photo_path': local_photo,
                    'short_card_photo_url': short_card_photo_url,
                    'short_card_local_photo_path': short_card_local_photo,
                    'long_card_photo_url': long_card_photo_url,
                    'long_card_local_photo_path': long_card_local_photo,
                    'loose_photo_url': loose_photo_url,
                    'loose_local_photo_path': loose_local_photo,
                }
                _, was_created = HotWheelsModel.objects.update_or_create(app_id=app_id, defaults=defaults)
                if was_created:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Import complete. Files: {imported_files}, created: {created}, updated: {updated}'
            )
        )

    def resolve_dataset_files(self, options) -> list[Path]:
        path_value = options.get('path')
        if path_value:
            path = Path(path_value)
            if not path.exists():
                raise CommandError(f'File not found: {path}')
            if path.suffix.lower() != '.json':
                raise CommandError(f'Unsupported file type: {path}')
            return [path]

        root = Path(options['root'])
        if not root.exists():
            raise CommandError(f'Dataset root not found: {root}')

        dataset_files = []
        for path in sorted(root.rglob('*.json')):
            metadata = self.extract_metadata_from_path(path)
            if options.get('brand') and metadata['brand_slug'] != options['brand'].strip().lower():
                continue
            if options.get('line') and metadata['line_slug'] != options['line'].strip().lower():
                continue
            if options.get('year') and metadata['year'] != options['year']:
                continue
            dataset_files.append(path)

        if dataset_files:
            return dataset_files

        raise CommandError('No dataset files matched the provided filters.')

    @staticmethod
    def load_rows(path: Path) -> list[dict]:
        try:
            payload = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            raise CommandError(f'Invalid JSON in {path}: {exc}') from exc
        if not isinstance(payload, list):
            raise CommandError(f'Expected a list of rows in {path}')
        return payload

    @classmethod
    def extract_metadata_from_path(cls, path: Path) -> dict:
        parts = path.parts
        if len(parts) < 3:
            return {
                'brand_slug': '',
                'line_slug': '',
                'brand': '',
                'category': '',
                'year': None,
            }

        year = None
        brand_slug = ''
        line_slug = ''
        if re.fullmatch(r'\d{4}', path.stem):
            brand_slug = parts[-3]
            line_slug = parts[-2]
            try:
                year = int(path.stem)
            except ValueError:
                pass
        elif len(parts) >= 4 and re.fullmatch(r'\d{4}', parts[-2]):
            brand_slug = parts[-4]
            line_slug = parts[-3]
            try:
                year = int(parts[-2])
            except ValueError:
                pass

        if not brand_slug or not line_slug:
            return {
                'brand_slug': '',
                'line_slug': '',
                'brand': '',
                'category': '',
                'year': None,
            }

        return {
            'brand_slug': brand_slug,
            'line_slug': line_slug,
            'brand': cls.slug_to_label(brand_slug) if year is not None else '',
            'category': cls.slug_to_label(line_slug) if year is not None else '',
            'year': year,
        }

    @staticmethod
    def slug_to_label(value: str) -> str:
        upper_tokens = {'rlc', 'sth', 'nft'}
        words = []
        for token in value.replace('_', '-').split('-'):
            if not token:
                continue
            words.append(token.upper() if token in upper_tokens else token.capitalize())
        return ' '.join(words)

    @staticmethod
    def clean_optional_text(value) -> str:
        if value is None:
            return ''
        return str(value).strip()

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
    def extract_year(row: dict, metadata: dict | None = None) -> int | None:
        if row.get('Year'):
            try:
                return int(row['Year'])
            except (TypeError, ValueError):
                pass

        if metadata and metadata.get('year'):
            return metadata['year']

        series = row.get('Series', '')
        match = re.search(r'(?:for|in)\s+(\d{4})', series)
        if match:
            return int(match.group(1))

        # Current repository dataset comes from the 2022 Hot Wheels page.
        return 2022

    @staticmethod
    def extract_category(row: dict, metadata: dict | None = None) -> str:
        if row.get('Category'):
            return str(row['Category']).strip()
        if metadata and metadata.get('category'):
            return metadata['category']
        return 'Mainline'

    @staticmethod
    def extract_brand(row: dict, metadata: dict | None = None) -> str:
        if row.get('Brand'):
            return str(row['Brand']).strip()
        if metadata and metadata.get('brand'):
            return metadata['brand']
        return 'Hot Wheels'

    @classmethod
    def clean_series(cls, value: str) -> str:
        cleaned = value or ''
        for marker in cls.SERIES_MARKERS:
            cleaned = cleaned.replace(marker, ' ')
        return re.sub(r'\s+', ' ', cleaned).strip()
