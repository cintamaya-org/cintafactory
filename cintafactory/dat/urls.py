from django.urls import include, path
from django.views.generic import RedirectView
from . import views

app_name = "dat"

urlpatterns = [
    # Redirect base index
    path("", RedirectView.as_view(url="my/", permanent=False), name="index"),

    # Main "My DAT" list
    path("my/", views.DatList.as_view(), name="my_list"),

    # Dashboard
    path("manage/dats/dashboard/", views.DatDashboardView.as_view(), name="dashboard"),

    # CRUD
    path("manage/dats/crud/", include(views.DATViewSet().urls)),
]
