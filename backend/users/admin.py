from django.contrib import admin

from .models import User


class UserAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'username',
        'email',
        'first_name',
        'last_name',
    )
    list_display_links = (
        'id',
        'username',
    )
    list_filter = ('email', 'username')


admin.site.register(User, UserAdmin)
