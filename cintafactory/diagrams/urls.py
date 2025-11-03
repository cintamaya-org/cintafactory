from django.urls import path

from . import views

app_name = "diagrams"

urlpatterns = [
    path("", views.DiagramListView.as_view(), name="list"),
    path("new/", views.DiagramCreateView.as_view(), name="create"),
    path("<int:pk>/", views.DiagramDetailView.as_view(), name="detail"),
    path("<int:pk>/edit/", views.DiagramEditView.as_view(), name="edit"),
    path("<int:pk>/save/", views.diagram_save_xml, name="save_xml"),
    path("<int:pk>/thumbnail/", views.diagram_save_thumbnail, name="save_thumbnail"),
]
