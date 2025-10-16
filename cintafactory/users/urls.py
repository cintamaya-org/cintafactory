from django.urls import include, path
from django.views import generic
from django.views.generic import RedirectView
from . import views

app_name = "users"

urlpatterns = [
    path("", RedirectView.as_view(url="manage/users/", permanent=False), name="index"),

    # Roles — list (ListView) and CRUD (ModelViewSet)
    path("manage/roles/", views.RoleList.as_view(), name="role_list"),
    # redirect ONLY the empty base of the viewset to the list page
    path("manage/roles/crud/", RedirectView.as_view(url="/users/manage/roles/", permanent=False)),
    path("manage/roles/crud/", include(views.RoleViewSet().urls)),

    # Users — list (ListView) and CRUD (ModelViewSet)
    path("manage/users/", views.UserList.as_view(), name="user_list"),
    path("manage/users/crud/", RedirectView.as_view(url="/users/manage/users/", permanent=False)),
    path("manage/users/crud/", include(views.UserViewSet().urls)),
]