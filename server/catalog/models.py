from django.conf import settings
from django.db import models
from django.urls import reverse


class HotWheelsModel(models.Model):
    app_id = models.CharField(max_length=64, unique=True)
    toy = models.CharField(max_length=32)
    number = models.CharField(max_length=16)
    model_name = models.CharField(max_length=255)
    series = models.CharField(max_length=255, blank=True)
    series_number = models.CharField(max_length=32, blank=True)
    photo_url = models.URLField(blank=True)
    local_photo_path = models.CharField(max_length=512, blank=True)

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

    @property
    def image_src(self) -> str:
        if self.local_photo_exists:
            return f'{settings.MEDIA_URL}{self.local_photo_path}'
        return self.photo_url
