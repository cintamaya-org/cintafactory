from django.contrib import admin

from .models import Diagram, LikeC4File


@admin.register(Diagram)
class DiagramAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "owner", "updated_at")
    search_fields = ("title", "owner__username")


@admin.register(LikeC4File)
class LikeC4FileAdmin(admin.ModelAdmin):
    list_display = ("id", "storage_path", "size", "updated_at")
    search_fields = ("storage_path",)
