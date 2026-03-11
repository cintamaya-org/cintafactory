from django.contrib import admin

from .models import DatViewflowProcess


@admin.register(DatViewflowProcess)
class DatViewflowProcessAdmin(admin.ModelAdmin):
    list_display = ("id", "dat", "process_id")
    search_fields = ("dat__reference", "dat__title", "process_id")
    readonly_fields = ("id",)
