from django.conf import settings
from django.db import models
from django.urls import reverse


class HotWheelsModel(models.Model):
    app_id = models.CharField(max_length=64, unique=True)
    brand = models.CharField(max_length=64, default='Hot Wheels')
    toy = models.CharField(max_length=32)
    number = models.CharField(max_length=16)
    model_name = models.CharField(max_length=255)
    year = models.PositiveIntegerField(blank=True, null=True)
    category = models.CharField(max_length=64, blank=True)
    series = models.CharField(max_length=255, blank=True)
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

    def get_absolute_url(self):
        return reverse('catalog:model-detail', args=[self.pk])

    @property
    def local_photo_exists(self) -> bool:
        if not self.local_photo_path:
            return False
        return (settings.PROJECT_ROOT / self.local_photo_path).exists()

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
        return (settings.PROJECT_ROOT / local_path).exists()

    @property
    def image_src(self) -> str:
        if self.local_photo_exists:
            return f'{settings.MEDIA_URL}{self.local_photo_path}'
        return self.photo_url

    def image_src_for_packaging(self, packaging_state: str) -> str:
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
            return f"{settings.MEDIA_URL}{getattr(self, path_attr)}"

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
