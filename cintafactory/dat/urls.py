from django.urls import include, path
from django.views.generic import RedirectView
from . import views

app_name = "dat"

urlpatterns = [
    # Redirect base index
    path("", RedirectView.as_view(url="my/", permanent=False), name="index"),

    # Main "My DAT" list
    path("my/", views.DatList.as_view(), name="my_list"),
    path("my/<int:pk>/", views.DatDetail.as_view(), name="my_detail"),
    path("my/<int:pk>/advance/", views.DatAdvanceStatusView.as_view(), name="my_advance"),
    path("my/<int:pk>/export/json/", views.DatExportJSONView.as_view(), name="my_export_json"),
    path(
        "my/<int:pk>/export/pdf/trigger/",
        views.DatTriggerPDFExportView.as_view(),
        name="my_export_pdf_trigger",
    ),
    path(
        "my/<int:pk>/export/pdf/status/",
        views.DatExportStatusView.as_view(),
        name="my_export_pdf_status",
    ),
    path(
        "my/<int:pk>/export/pdf/generate/",
        views.DatGeneratePDFExportView.as_view(),
        name="my_export_pdf_generate",
    ),
    path(
        "my/<int:pk>/export/pdf/download/",
        views.DatDownloadCachedPDFView.as_view(),
        name="my_export_pdf_download",
    ),
    path(  # Backward compatibility alias
        "my/<int:pk>/export/pdf/",
        views.DatGeneratePDFExportView.as_view(),
        name="my_export_pdf",
    ),
    path(
        "my/<int:dat_pk>/sections/<slug:section_slug>/<slug:sub_section_slug>/edit/",
        views.DatSubSectionUpdateView.as_view(),
        name="sub_section_edit",
    ),
    path(
        "my/<int:dat_pk>/schemas/create-diagram/",
        views.create_schema_diagram,
        name="schema_create_diagram",
    ),

    # Dashboard
    path("manage/dats/dashboard/", views.DatDashboardView.as_view(), name="dashboard"),

    # CRUD
    path("manage/dats/crud/", views.DatAdminList.as_view(), name="admin_list"),
    path("manage/dats/crud/", include(views.DATViewSet().urls)),
    path("manage/applications/options/", views.application_options, name="application_options"),
    path("manage/applications/crud/", include(views.ApplicationViewSet().urls)),
]
