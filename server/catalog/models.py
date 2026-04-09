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
        if category in {'premium', 'semi premium', 'xl', 'rlc', '5 pack'} or self.exclusive_store:
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
        return (settings.CATALOG_SOURCE_ROOT / self.local_photo_path).exists()

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
        return (settings.CATALOG_SOURCE_ROOT / local_path).exists()

    @property
    def image_src(self) -> str:
        if self.local_photo_path:
            variant_src = self.image_variant_src_for_relative_path(self.local_photo_path, 'detail', self.photo_url)
            if variant_src:
                return variant_src
        return self.photo_url

    def image_src_for_packaging(self, packaging_state: str, variant_name: str = 'detail') -> str:
        if packaging_state not in self.available_packaging_states:
            return ''

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

        if path_attr and self.local_packaging_photo_exists(packaging_state):
            return self.image_variant_src_for_relative_path(getattr(self, path_attr), variant_name, getattr(self, url_attr) or self.photo_url)

        if url_attr and getattr(self, url_attr):
            return getattr(self, url_attr)

        return self.image_src

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
        if packaging_state not in self.available_packaging_states:
            return False

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
            return False
        return bool(getattr(self, path_attr) or getattr(self, url_attr))

    @property
    def catalog_image_variants(self) -> list[dict]:
        return self.catalog_image_variants_for_usage()

    def catalog_image_variants_for_usage(self, variant_name: str = 'detail') -> list[dict]:
        variants = []
        for packaging_state, label in self.available_packaging_choices:
            if not self.has_packaging_image(packaging_state):
                continue
            variants.append(
                {
                    'key': packaging_state,
                    'label': label,
                    'src': self.image_src_for_packaging(packaging_state, variant_name),
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
                'src': self.image_src_for_packaging(packaging_state, variant_name),
            }
            for packaging_state, label in self.available_packaging_choices
            if self.image_src_for_packaging(packaging_state, variant_name)
        ]
