from django.contrib import admin

from .models import Collection, CollectionItem


class CollectionItemInline(admin.TabularInline):
    model = CollectionItem
    extra = 0


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'visibility', 'created_at')
    list_filter = ('visibility',)
    search_fields = ('name', 'owner__email')
    inlines = [CollectionItemInline]


@admin.register(CollectionItem)
class CollectionItemAdmin(admin.ModelAdmin):
    list_display = (
        'collection',
        'model',
        'quantity',
        'condition',
        'packaging_state',
        'is_sealed',
        'has_soft_corners',
        'has_protector',
        'is_signed',
        'has_bent_hook',
        'has_cracked_blister',
        'is_favorite',
    )
    list_filter = (
        'condition',
        'packaging_state',
        'is_sealed',
        'has_soft_corners',
        'has_protector',
        'is_signed',
        'has_bent_hook',
        'has_cracked_blister',
        'is_favorite',
    )
    search_fields = ('collection__name', 'collection__owner__email', 'model__model_name')
