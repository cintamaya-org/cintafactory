from django.urls import path

from . import views

app_name = "diagrams"

urlpatterns = [
    path("drawio/proxy/", views.drawio_proxy, name="drawio_proxy_root"),
    path("drawio/proxy/<path:path>", views.drawio_proxy, name="drawio_proxy"),
    path("", views.DiagramListView.as_view(), name="list"),
    path("new/", views.DiagramCreateView.as_view(), name="create"),
    path("<int:pk>/", views.DiagramDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.DiagramEditView.as_view(), name="edit"),
    path("<int:pk>/embed-context/", views.diagram_embed_context, name="embed_context"),
    path("<int:pk>/viewer-context/", views.diagram_viewer_context, name="viewer_context"),
    path("<int:pk>/save/", views.diagram_save_xml, name="save_xml"),
    path("<int:pk>/thumbnail/", views.diagram_save_thumbnail, name="save_thumbnail"),
    path("<int:pk>/import/", views.diagram_import_xml, name="import_xml"),
    path("<int:pk>/export/", views.diagram_export_xml, name="export_xml"),
]
