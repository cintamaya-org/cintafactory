from django.contrib import admin

from .models import (
    Application,
    DAT,
    DATExportAccessApproval,
    DATExportAccessHistory,
    DATExportAccessRequest,
    DATParticipant,
    DATSectionAttachment,
)


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "business_direction", "formatted_created_at", "formatted_updated_at")
    search_fields = ("code", "name", "business_direction__name")
    ordering = ("name",)


class DATParticipantInline(admin.TabularInline):
    model = DATParticipant
    extra = 0
    autocomplete_fields = ("user", "role")
    readonly_fields = ("created_at",)


@admin.register(DAT)
class DATAdmin(admin.ModelAdmin):
    list_display = ("reference", "title", "application", "business_direction", "status", "owner", "created_at")
    list_filter = ("status", "created_at", "application", "business_direction")
    search_fields = ("reference", "title", "description", "application__name", "business_direction__name")
    ordering = ("-created_at",)
    inlines = (DATParticipantInline,)


@admin.register(DATSectionAttachment)
class DATSectionAttachmentAdmin(admin.ModelAdmin):
    list_display = ("display_name", "section", "uploaded_by", "size", "created_at")
    list_filter = ("created_at", "section__dat__reference")
    search_fields = ("display_name", "original_name", "section__title", "section__dat__reference")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)


@admin.register(DATExportAccessRequest)
class DATExportAccessRequestAdmin(admin.ModelAdmin):
    list_display = ("dat", "status", "requested_by", "requested_at", "approve_deadline_at", "access_valid_until")
    list_filter = ("status", "requested_at")
    search_fields = ("dat__reference", "dat__title", "requested_by__username")
    ordering = ("-requested_at",)


@admin.register(DATExportAccessApproval)
class DATExportAccessApprovalAdmin(admin.ModelAdmin):
    list_display = ("dat", "request", "approved_by", "approved_at")
    list_filter = ("approved_at",)
    search_fields = ("dat__reference", "approved_by__username")
    ordering = ("-approved_at",)


@admin.register(DATExportAccessHistory)
class DATExportAccessHistoryAdmin(admin.ModelAdmin):
    list_display = ("dat", "event_type", "actor", "created_at")
    list_filter = ("event_type", "created_at")
    search_fields = ("dat__reference", "actor__username")
    ordering = ("-created_at",)
