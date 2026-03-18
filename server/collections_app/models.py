from django.conf import settings
from django.db import models
from django.urls import reverse

from catalog.models import HotWheelsModel


class Collection(models.Model):
    KIND_OWNED = 'owned'
    KIND_WISHLIST = 'wishlist'
    KIND_CHOICES = (
        (KIND_OWNED, 'Kolekcja'),
        (KIND_WISHLIST, 'Wishlist'),
    )
    VISIBILITY_PRIVATE = 'private'
    VISIBILITY_PUBLIC = 'public'
    VISIBILITY_CHOICES = (
        (VISIBILITY_PRIVATE, 'Prywatna'),
        (VISIBILITY_PUBLIC, 'Publiczna'),
    )

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='collections')
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    kind = models.CharField(max_length=12, choices=KIND_CHOICES, default=KIND_OWNED)
    visibility = models.CharField(max_length=10, choices=VISIBILITY_CHOICES, default=VISIBILITY_PRIVATE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('name',)
        unique_together = ('owner', 'name')

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self):
        return reverse('collections:collection-detail', args=[self.pk])

    @property
    def is_public(self) -> bool:
        return self.visibility == self.VISIBILITY_PUBLIC

    @property
    def is_wishlist(self) -> bool:
        return self.kind == self.KIND_WISHLIST


class CollectionItem(models.Model):
    CONDITION_CHOICES = (
        ('mint', 'Mint'),
        ('good', 'Good'),
        ('used', 'Used'),
    )
    PACKAGING_CHOICES = (
        ('short_card', 'Krótka karta'),
        ('long_card', 'Długa karta'),
        ('loose', 'Luzak'),
    )

    collection = models.ForeignKey(Collection, on_delete=models.CASCADE, related_name='items')
    model = models.ForeignKey(HotWheelsModel, on_delete=models.CASCADE, related_name='collection_items')
    quantity = models.PositiveIntegerField(default=1)
    condition = models.CharField(max_length=16, choices=CONDITION_CHOICES, default='good')
    packaging_state = models.CharField(max_length=16, choices=PACKAGING_CHOICES, default='short_card')
    is_sealed = models.BooleanField(default=False)
    has_soft_corners = models.BooleanField(default=False)
    has_protector = models.BooleanField(default=False)
    is_signed = models.BooleanField(default=False)
    acquired_at = models.DateField(blank=True, null=True)
    notes = models.TextField(blank=True)
    is_favorite = models.BooleanField(default=False)

    class Meta:
        ordering = ('-is_favorite', 'model__number', 'model__model_name', 'packaging_state', 'condition')
        unique_together = (
            'collection',
            'model',
            'packaging_state',
            'condition',
            'is_sealed',
            'has_soft_corners',
            'has_protector',
            'is_signed',
        )

    def __str__(self) -> str:
        return f'{self.collection} - {self.model}'

    @property
    def image_src(self) -> str:
        return self.model.image_src_for_packaging(self.packaging_state)

    @property
    def attribute_badges(self) -> list[str]:
        badges = []
        if self.is_sealed:
            badges.append('Sealed')
        if self.has_soft_corners:
            badges.append('Soft corners')
        if self.has_protector:
            badges.append('Protector')
        if self.is_signed:
            badges.append('Signed')
        return badges
