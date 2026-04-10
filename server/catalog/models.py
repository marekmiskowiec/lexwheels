from django.conf import settings
from django.db import models
from django.urls import reverse
from pathlib import Path


class HotWheelsModel(models.Model):
    PACKAGING_LABELS = (
        ('short_card', 'Krótka'),
        ('long_card', 'Długa'),
        ('loose', 'Luzak'),
    )
    IMAGE_VARIANT_NAMES = ('thumb', 'preview', 'detail')
    app_id = models.CharField(max_length=64, unique=True)
    brand = models.CharField(max_length=64, default='Hot Wheels')
    toy = models.CharField(max_length=32)
    number = models.CharField(max_length=16)
    model_name = models.CharField(max_length=255)
    year = models.PositiveIntegerField(blank=True, null=True)
    category = models.CharField(max_length=64, blank=True)
    series = models.CharField(max_length=255, blank=True)
    exclusive_store = models.CharField(max_length=128, blank=True)
    special_tag = models.CharField(max_length=128, blank=True)
    case_codes = models.CharField(max_length=64, blank=True)
    series_number = models.CharField(max_length=32, blank=True)
    photo_url = models.URLField(blank=True)
    local_photo_path = models.CharField(max_length=512, blank=True)
    short_card_photo_url = models.URLField(blank=True)
    short_card_local_photo_path = models.CharField(max_length=512, blank=True)
    long_card_photo_url = models.URLField(blank=True)
    long_card_local_photo_path = models.CharField(max_length=512, blank=True)
    loose_photo_url = models.URLField(blank=True)
    loose_local_photo_path = models.CharField(max_length=512, blank=True)
    images_verified_at = models.DateTimeField(blank=True, null=True)
    images_verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name='verified_catalog_models',
    )

    class Meta:
        ordering = ('number', 'model_name')
        verbose_name = 'Hot Wheels model'
        verbose_name_plural = 'Hot Wheels models'

    def __str__(self) -> str:
        return f'{self.number} {self.model_name}'

    @property
    def packaging_labels(self) -> dict[str, str]:
        return dict(self.PACKAGING_LABELS)

    @property
    def excluded_packaging_states(self) -> set[str]:
        category = (self.category or '').strip().lower()
        if category == 'xl':
            return {'long_card'}
        if category in {'premium', 'semi premium', 'rlc', '5 pack'} or self.exclusive_store:
            return {'short_card'}
        return set()

    @property
    def available_packaging_states(self) -> list[str]:
        return [
            packaging_state
            for packaging_state, _ in self.PACKAGING_LABELS
            if packaging_state not in self.excluded_packaging_states
        ]

    @property
    def available_packaging_choices(self) -> list[tuple[str, str]]:
        return [
            (packaging_state, label)
            for packaging_state, label in self.PACKAGING_LABELS
            if packaging_state in self.available_packaging_states
        ]

    def get_absolute_url(self):
        return reverse('catalog:model-detail', args=[self.pk])

    @property
    def case_code_list(self) -> list[str]:
        return [code.strip() for code in self.case_codes.split(',') if code.strip()]

    @property
    def local_photo_exists(self) -> bool:
        if not self.local_photo_path:
            return False
        return any(self.image_variant_exists(self.local_photo_path, variant_name) for variant_name in self.IMAGE_VARIANT_NAMES)

    @staticmethod
    def build_image_variant_relative_path(relative_path: str, variant_name: str) -> str:
        if not relative_path or variant_name not in HotWheelsModel.IMAGE_VARIANT_NAMES:
            return ''
        source_path = Path(relative_path)
        return str(source_path.with_name(f'{source_path.stem}--{variant_name}.webp'))

    def image_variant_exists(self, relative_path: str, variant_name: str) -> bool:
        variant_relative_path = self.build_image_variant_relative_path(relative_path, variant_name)
        if not variant_relative_path:
            return False
        return (settings.MEDIA_ROOT / variant_relative_path).exists()

    @staticmethod
    def media_src_for_relative_path(relative_path: str) -> str:
        if not relative_path:
            return ''
        return f'{settings.MEDIA_URL}{relative_path}'

    def image_variant_src_for_relative_path(self, relative_path: str, variant_name: str, fallback_src: str = '') -> str:
        if self.image_variant_exists(relative_path, variant_name):
            return self.media_src_for_relative_path(self.build_image_variant_relative_path(relative_path, variant_name))
        return fallback_src

    def local_packaging_photo_exists(self, packaging_state: str) -> bool:
        path_attr = {
            'short_card': 'short_card_local_photo_path',
            'long_card': 'long_card_local_photo_path',
            'loose': 'loose_local_photo_path',
        }.get(packaging_state)
        if not path_attr:
            return self.local_photo_exists

        local_path = getattr(self, path_attr, '')
        if not local_path:
            return False
        return any(self.image_variant_exists(local_path, variant_name) for variant_name in self.IMAGE_VARIANT_NAMES)

    @property
    def image_src(self) -> str:
        if self.local_photo_path:
            variant_src = self.image_variant_src_for_relative_path(self.local_photo_path, 'detail', self.photo_url)
            if variant_src:
                return variant_src
        return self.photo_url

    def generic_image_reference(self) -> dict[str, str]:
        return {
            'local_path': self.local_photo_path,
            'url': self.photo_url,
        }

    def packaging_image_reference(self, packaging_state: str) -> dict[str, str]:
        path_attr = {
            'short_card': 'short_card_local_photo_path',
            'long_card': 'long_card_local_photo_path',
            'loose': 'loose_local_photo_path',
        }.get(packaging_state)
        url_attr = {
            'short_card': 'short_card_photo_url',
            'long_card': 'long_card_photo_url',
            'loose': 'loose_photo_url',
        }.get(packaging_state)
        if not path_attr or not url_attr:
            return {'local_path': '', 'url': ''}
        return {
            'local_path': getattr(self, path_attr, ''),
            'url': getattr(self, url_attr, ''),
        }

    @staticmethod
    def image_reference_signature(reference: dict[str, str]) -> tuple[str, str]:
        local_path = (reference.get('local_path') or '').strip()
        url = (reference.get('url') or '').strip()
        if local_path:
            return ('local', local_path)
        if url:
            return ('url', url)
        return ('', '')

    def image_src_for_reference(self, reference: dict[str, str], variant_name: str = 'detail') -> str:
        local_path = (reference.get('local_path') or '').strip()
        url = (reference.get('url') or '').strip()
        if local_path:
            variant_src = self.image_variant_src_for_relative_path(local_path, variant_name, url)
            if variant_src:
                return variant_src
        return url

    def duplicated_packaging_image_signature(self) -> tuple[str, str]:
        signatures = []
        for packaging_state in self.available_packaging_states:
            signature = self.image_reference_signature(self.packaging_image_reference(packaging_state))
            if signature != ('', ''):
                signatures.append(signature)
        if len(signatures) >= 2 and len(set(signatures)) == 1:
            return signatures[0]
        return ('', '')

    def duplicated_packaging_image_reference(self) -> dict[str, str] | None:
        duplicate_signature = self.duplicated_packaging_image_signature()
        if duplicate_signature == ('', ''):
            return None
        for packaging_state in self.available_packaging_states:
            reference = self.packaging_image_reference(packaging_state)
            if self.image_reference_signature(reference) == duplicate_signature:
                return reference
        return None

    def image_src_for_packaging(self, packaging_state: str, variant_name: str = 'detail') -> str:
        if packaging_state not in self.available_packaging_states:
            return ''
        reference = self.display_packaging_image_reference(packaging_state)
        if not reference:
            return ''
        return self.image_src_for_reference(reference, variant_name)

    @property
    def short_card_image_src(self) -> str:
        return self.image_src_for_packaging('short_card')

    @property
    def long_card_image_src(self) -> str:
        return self.image_src_for_packaging('long_card')

    @property
    def loose_image_src(self) -> str:
        return self.image_src_for_packaging('loose')

    def has_packaging_image(self, packaging_state: str) -> bool:
        return bool(self.display_packaging_image_reference(packaging_state))

    def display_packaging_image_reference(self, packaging_state: str) -> dict[str, str] | None:
        if packaging_state not in self.available_packaging_states:
            return None

        packaging_reference = self.packaging_image_reference(packaging_state)
        packaging_signature = self.image_reference_signature(packaging_reference)
        duplicate_signature = self.duplicated_packaging_image_signature()
        if duplicate_signature != ('', '') and packaging_signature == duplicate_signature:
            return None
        if packaging_signature != ('', ''):
            return packaging_reference
        return None

    @property
    def unassigned_image_reference(self) -> dict[str, str] | None:
        if not self.missing_packaging_image_states:
            return None
        generic_reference = self.generic_image_reference()
        if self.image_reference_signature(generic_reference) == ('', ''):
            return self.duplicated_packaging_image_reference()
        return generic_reference

    @property
    def unassigned_image_src(self) -> str:
        if not self.unassigned_image_reference:
            return ''
        return self.image_src_for_reference(self.unassigned_image_reference)

    @property
    def has_unassigned_image(self) -> bool:
        return bool(self.unassigned_image_reference)

    @property
    def has_complete_packaging_images(self) -> bool:
        return not self.has_unassigned_image and not self.missing_packaging_image_states

    @property
    def images_verified(self) -> bool:
        return bool(self.images_verified_at)

    @property
    def missing_packaging_image_states(self) -> list[str]:
        return [
            packaging_state
            for packaging_state in self.available_packaging_states
            if not self.display_packaging_image_reference(packaging_state)
        ]

    @property
    def missing_packaging_image_choices(self) -> list[tuple[str, str]]:
        return [
            (packaging_state, label)
            for packaging_state, label in self.available_packaging_choices
            if packaging_state in self.missing_packaging_image_states
        ]

    @property
    def catalog_image_variants(self) -> list[dict]:
        return self.catalog_image_variants_for_usage()

    def catalog_image_variants_for_usage(self, variant_name: str = 'detail') -> list[dict]:
        variants = []
        for packaging_state, label in self.available_packaging_choices:
            reference = self.display_packaging_image_reference(packaging_state)
            if not reference:
                continue
            variants.append(
                {
                    'key': packaging_state,
                    'label': label,
                    'src': self.image_src_for_reference(reference, variant_name),
                }
            )

        if variants:
            return variants

        if self.image_src:
            src = self.image_variant_src_for_relative_path(self.local_photo_path, variant_name, self.image_src) if self.local_photo_path else self.image_src
            return [{'key': 'default', 'label': 'Zdjęcie', 'src': src}]

        return []

    @property
    def catalog_primary_image_src(self) -> str:
        return self.catalog_primary_image_src_for_usage()

    def catalog_primary_image_src_for_usage(self, variant_name: str = 'detail') -> str:
        variants = self.catalog_image_variants_for_usage(variant_name)
        if not variants:
            return ''

        preferred_variant_order = ('long_card', 'short_card', 'loose', 'default')
        variant_src_by_key = {variant['key']: variant['src'] for variant in variants}
        for key in preferred_variant_order:
            if variant_src_by_key.get(key):
                return variant_src_by_key[key]

        return variants[0]['src']

    @property
    def catalog_primary_thumb_src(self) -> str:
        return self.catalog_primary_image_src_for_usage('thumb')

    @property
    def catalog_primary_preview_src(self) -> str:
        return self.catalog_primary_image_src_for_usage('preview')

    @property
    def packaging_image_panels(self) -> list[dict]:
        return self.packaging_image_panels_for_usage()

    def packaging_image_panels_for_usage(self, variant_name: str = 'detail') -> list[dict]:
        return [
            {
                'key': packaging_state,
                'label': label,
                'src': self.image_src_for_reference(reference, variant_name),
            }
            for packaging_state, label in self.available_packaging_choices
            for reference in [self.display_packaging_image_reference(packaging_state)]
            if reference
        ]
