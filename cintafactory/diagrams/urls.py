from django.urls import path

from . import views

app_name = "diagrams"

urlpatterns = [
    path("drawio/proxy/", views.drawio_proxy, name="drawio_proxy_root"),
    path("drawio/proxy/<path:path>", views.drawio_proxy, name="drawio_proxy"),
    path("likec4/editor/", views.likec4_proxy, name="likec4_proxy_root"),
    path("likec4/editor/<path:path>", views.likec4_proxy, name="likec4_proxy"),
    path("", views.DiagramListView.as_view(), name="list"),
    path("new/", views.DiagramCreateView.as_view(), name="create"),
    path("<int:pk>/", views.DiagramDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.DiagramEditView.as_view(), name="edit"),
    path("<int:pk>/embed-context/", views.diagram_embed_context, name="embed_context"),
    path("<int:pk>/viewer-context/", views.diagram_viewer_context, name="viewer_context"),
    path("<int:pk>/asset/<path:asset_path>", views.diagram_asset, name="diagram_asset"),
    path("<int:pk>/save/", views.diagram_save_xml, name="save_xml"),
    path("<int:pk>/thumbnail/", views.diagram_save_thumbnail, name="save_thumbnail"),
    path("<int:pk>/import/", views.diagram_import_xml, name="import_xml"),
    path("<int:pk>/export/", views.diagram_export_xml, name="export_xml"),
    path("likec4/metadata/", views.likec4_metadata, name="likec4_metadata"),
    path("likec4/import/", views.likec4_import, name="likec4_import"),
    path("likec4/png/", views.likec4_png, name="likec4_png"),
    path("likec4/views/", views.likec4_views, name="likec4_views"),
    path("likec4/export/", views.likec4_export, name="likec4_export"),
]
