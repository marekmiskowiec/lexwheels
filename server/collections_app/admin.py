from django.contrib import admin

from .models import Collection, CollectionItem, ImportBacklogEntry, ImportBacklogReport


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


@admin.register(ImportBacklogEntry)
class ImportBacklogEntryAdmin(admin.ModelAdmin):
    list_display = (
        'model_name',
        'toy',
        'year',
        'category',
        'series',
        'status',
        'report_count',
        'last_seen_at',
    )
    list_filter = ('status', 'category', 'year')
    search_fields = ('model_name', 'toy', 'series')


@admin.register(ImportBacklogReport)
class ImportBacklogReportAdmin(admin.ModelAdmin):
    list_display = ('backlog_entry', 'owner', 'collection', 'color', 'import_count', 'last_seen_at')
    list_filter = ('owner',)
    search_fields = ('backlog_entry__model_name', 'owner__email', 'owner__login', 'color')
