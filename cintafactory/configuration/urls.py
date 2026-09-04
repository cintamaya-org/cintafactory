from django.urls import path

from . import views

app_name = "configuration"

urlpatterns = [
    path("", views.ConfigurationHomeView.as_view(), name="index"),
]
