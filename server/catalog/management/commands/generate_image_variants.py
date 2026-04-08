import subprocess
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from catalog.models import HotWheelsModel


class Command(BaseCommand):
    help = 'Generate optimized thumb/preview/detail webp variants for local catalog images.'
    VARIANT_WIDTHS = {
        'thumb': 320,
        'preview': 960,
        'detail': 1400,
    }
    WEBP_QUALITY = 82

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true', help='Regenerate variants even if they already exist.')
        parser.add_argument('--limit', type=int, help='Process only the first N unique source images.')

    def handle(self, *args, **options):
        cwebp_binary = subprocess.run(
            ['which', 'cwebp'],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        if not cwebp_binary:
            raise CommandError('cwebp binary not found in PATH.')

        source_paths = self.collect_source_paths(limit=options.get('limit'))
        if not source_paths:
            self.stdout.write('No local images found.')
            return

        generated = 0
        skipped = 0

        for relative_path in source_paths:
            source_path = settings.PROJECT_ROOT / relative_path
            if not source_path.exists():
                continue

            for variant_name, width in self.VARIANT_WIDTHS.items():
                destination_relative_path = HotWheelsModel.build_image_variant_relative_path(relative_path, variant_name)
                destination_path = settings.PROJECT_ROOT / destination_relative_path
                destination_path.parent.mkdir(parents=True, exist_ok=True)

                if (
                    destination_path.exists()
                    and not options['force']
                    and destination_path.stat().st_mtime >= source_path.stat().st_mtime
                ):
                    skipped += 1
                    continue

                command = [
                    cwebp_binary,
                    '-quiet',
                    '-q',
                    str(self.WEBP_QUALITY),
                    '-resize',
                    str(width),
                    '0',
                    str(source_path),
                    '-o',
                    str(destination_path),
                ]
                subprocess.run(command, check=True)
                generated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Image variants complete. Sources: {len(source_paths)}, generated: {generated}, skipped: {skipped}'
            )
        )

    @staticmethod
    def collect_source_paths(limit: int | None = None) -> list[str]:
        relative_paths = []
        seen = set()
        queryset = HotWheelsModel.objects.values_list(
            'local_photo_path',
            'short_card_local_photo_path',
            'long_card_local_photo_path',
            'loose_local_photo_path',
        )
        for row in queryset.iterator():
            for relative_path in row:
                cleaned = (relative_path or '').strip()
                if not cleaned or cleaned in seen:
                    continue
                seen.add(cleaned)
                relative_paths.append(cleaned)
                if limit and len(relative_paths) >= limit:
                    return relative_paths
        return relative_paths
