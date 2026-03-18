from django.contrib import admin

from .models import HotWheelsModel


@admin.register(HotWheelsModel)
class HotWheelsModelAdmin(admin.ModelAdmin):
    list_display = ('number', 'toy', 'model_name', 'brand', 'year', 'category', 'series', 'series_number')
    list_filter = ('brand', 'year', 'category', 'series')
    search_fields = ('toy', 'number', 'model_name', 'brand', 'series')
