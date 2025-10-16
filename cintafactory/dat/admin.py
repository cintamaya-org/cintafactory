from django.contrib import admin
from .models import DAT

@admin.register(DAT)
class DATAdmin(admin.ModelAdmin):
    list_display = ("reference", "title", "status", "owner", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("reference", "title", "description")
    ordering = ("-created_at",)
