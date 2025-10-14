from django.contrib import admin
from .models import DAT, DATSequence

@admin.register(DAT)
class DATAdmin(admin.ModelAdmin):
    list_display = ("business_id", "title", "project_name", "status", "created_by", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("business_id", "title", "project_name", "created_by__username")
    readonly_fields = ("business_id", "created_at", "updated_at")

@admin.register(DATSequence)
class DATSequenceAdmin(admin.ModelAdmin):
    list_display = ("year", "last_number")
    readonly_fields = ("year", "last_number")
