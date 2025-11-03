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

    # Dashboard
    path("manage/dats/dashboard/", views.DatDashboardView.as_view(), name="dashboard"),

    # CRUD
    path("manage/dats/crud/", views.DatAdminList.as_view(), name="admin_list"),
    path("manage/dats/crud/", include(views.DATViewSet().urls)),
    path("manage/applications/options/", views.application_options, name="application_options"),
    path("manage/applications/crud/", include(views.ApplicationViewSet().urls)),
]
