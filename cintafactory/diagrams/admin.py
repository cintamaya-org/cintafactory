from django.contrib import admin

from .models import Diagram


@admin.register(Diagram)
class DiagramAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "owner", "updated_at")
    search_fields = ("title", "owner__username")
