from django.contrib import admin

from .models import Application, DAT, DATParticipant


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "formatted_created_at", "formatted_updated_at")
    search_fields = ("code", "name")
    ordering = ("name",)


class DATParticipantInline(admin.TabularInline):
    model = DATParticipant
    extra = 0
    autocomplete_fields = ("user", "role")
    readonly_fields = ("created_at",)


@admin.register(DAT)
class DATAdmin(admin.ModelAdmin):
    list_display = ("reference", "title", "application", "status", "owner", "created_at")
    list_filter = ("status", "created_at", "application")
    search_fields = ("reference", "title", "description", "application__name")
    ordering = ("-created_at",)
    inlines = (DATParticipantInline,)
