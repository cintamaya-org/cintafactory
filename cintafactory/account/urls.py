from django.urls import path

from . import views

app_name = "account"

urlpatterns = [
    path("", views.AccountProfileView.as_view(), name="index"),
    path("profile/", views.AccountProfileView.as_view(), name="profile"),
    path("password/change/", views.AccountPasswordChangeView.as_view(), name="password_change"),
    path("password/change/done/", views.AccountPasswordChangeDoneView.as_view(), name="password_change_done"),
]
