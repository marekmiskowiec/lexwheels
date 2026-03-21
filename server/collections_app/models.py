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
        ('mint', 'Idealny'),
        ('good', 'Dobry'),
        ('used', 'Używany'),
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
    has_bent_hook = models.BooleanField(default=False)
    has_cracked_blister = models.BooleanField(default=False)
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
            'has_bent_hook',
            'has_cracked_blister',
        )

    def __str__(self) -> str:
        return f'{self.collection} - {self.model}'

    @property
    def image_src(self) -> str:
        return self.model.image_src_for_packaging(self.packaging_state)

    @property
    def supports_card_attributes(self) -> bool:
        return self.packaging_state != 'loose'

    @property
    def attribute_badges(self) -> list[str]:
        if not self.supports_card_attributes:
            return []
        badges = []
        if self.is_sealed:
            badges.append('Zafoliowany')
        if self.has_soft_corners:
            badges.append('Miękkie rogi')
        if self.has_protector:
            badges.append('Protektor')
        if self.is_signed:
            badges.append('Podpisany')
        if self.has_bent_hook:
            badges.append('Zagięty haczyk')
        if self.has_cracked_blister:
            badges.append('Pęknięty blister')
        return badges


class WantedItem(models.Model):
    PACKAGING_ANY = 'any'
    PACKAGING_CHOICES = (
        (PACKAGING_ANY, 'Dowolne opakowanie'),
    ) + CollectionItem.PACKAGING_CHOICES

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wanted_items')
    model = models.ForeignKey(HotWheelsModel, on_delete=models.CASCADE, related_name='wanted_items')
    packaging_state = models.CharField(max_length=16, choices=PACKAGING_CHOICES, default=PACKAGING_ANY)
    condition_min = models.CharField(max_length=16, choices=CollectionItem.CONDITION_CHOICES, default='good')
    budget_max = models.DecimalField(max_digits=8, decimal_places=2, blank=True, null=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-is_active', '-updated_at', '-created_at')
        constraints = [
            models.UniqueConstraint(
                fields=('owner', 'model', 'packaging_state', 'condition_min'),
                name='unique_wanted_item_per_owner_variant',
            )
        ]

    def __str__(self) -> str:
        return f'{self.owner} szuka {self.model}'

    @property
    def has_social_links(self) -> bool:
        return bool(self.owner.youtube_url or self.owner.tiktok_url or self.owner.instagram_url)


class ImportBacklogEntry(models.Model):
    STATUS_OPEN = 'open'
    STATUS_RESOLVED = 'resolved'
    STATUS_IGNORED = 'ignored'
    STATUS_CHOICES = (
        (STATUS_OPEN, 'Otwarte'),
        (STATUS_RESOLVED, 'Rozwiązane'),
        (STATUS_IGNORED, 'Zignorowane'),
    )

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_OPEN)
    toy = models.CharField(max_length=64, blank=True)
    model_name = models.CharField(max_length=255)
    year = models.PositiveIntegerField(blank=True, null=True)
    category = models.CharField(max_length=64, blank=True)
    series = models.CharField(max_length=255, blank=True)
    series_number = models.CharField(max_length=32, blank=True)
    report_count = models.PositiveIntegerField(default=1)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    resolved_model = models.ForeignKey(
        HotWheelsModel,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='resolved_import_backlog_entries',
    )

    class Meta:
        ordering = ('status', '-last_seen_at', 'model_name')
        constraints = [
            models.UniqueConstraint(
                fields=('toy', 'model_name', 'year', 'category', 'series', 'series_number'),
                name='unique_global_import_backlog_entry',
            )
        ]

    def __str__(self) -> str:
        return self.model_name


class ImportBacklogReport(models.Model):
    backlog_entry = models.ForeignKey(ImportBacklogEntry, on_delete=models.CASCADE, related_name='reports')
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='import_backlog_reports')
    collection = models.ForeignKey(Collection, on_delete=models.SET_NULL, null=True, blank=True, related_name='import_backlog_reports')
    color = models.CharField(max_length=128, blank=True)
    price = models.CharField(max_length=128, blank=True)
    location = models.CharField(max_length=255, blank=True)
    source_payload = models.JSONField(default=dict, blank=True)
    import_count = models.PositiveIntegerField(default=1)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-last_seen_at',)
        constraints = [
            models.UniqueConstraint(
                fields=('backlog_entry', 'owner', 'collection', 'color'),
                name='unique_import_backlog_report_per_context',
            )
        ]

    def __str__(self) -> str:
        return f'{self.backlog_entry} | {self.owner}'
