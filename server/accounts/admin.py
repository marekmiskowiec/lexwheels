from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ('email',)
    list_display = ('email', 'login', 'display_name', 'avatar_key', 'is_staff')
    fieldsets = (
        (None, {'fields': ('email', 'login', 'password')}),
        ('Personal info', {'fields': ('display_name', 'bio', 'avatar_key')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'login', 'password1', 'password2'),
        }),
    )
    search_fields = ('email', 'login', 'display_name')
