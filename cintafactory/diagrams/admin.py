# SPDX-FileCopyrightText: 2026 Cintamaya <contact@cintamaya.com>
# SPDX-FileCopyrightText: 2026 Baptiste COQUELET <github.com/BaptisteCoquelet>
# SPDX-License-Identifier: AGPL-3.0-only

from django.contrib import admin

from .models import DrawIODiagram, LikeC4Diagram


@admin.register(DrawIODiagram)
class DiagramAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "owner", "updated_at")
    search_fields = ("title", "owner__username")


@admin.register(LikeC4Diagram)
class LikeC4DiagramAdmin(admin.ModelAdmin):
    list_display = ("id", "storage_path", "title", "size", "updated_at")
    search_fields = ("storage_path", "title")
