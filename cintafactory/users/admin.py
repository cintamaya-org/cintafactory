from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from .models import User, Role

@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "user_count")
    search_fields = ("name", "slug")
    ordering = ("name",)
    def user_count(self, obj): return obj.users.count()
    user_count.short_description = "Users"

@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "email")}),
        ("Role", {"fields": ("role", "architect_referent")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("username", "password1", "password2", "role", "architect_referent")}),)
    list_display = ("username", "email", "first_name", "last_name", "is_staff", "role", "architect_referent")
    list_filter = ("is_staff", "is_superuser", "is_active", "groups", "role", "architect_referent")
    search_fields = ("username", "first_name", "last_name", "email")
    ordering = ("username",)
