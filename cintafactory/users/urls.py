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

    # Groups — list and CRUD
    path("manage/groups/", views.BusinessGroupList.as_view(), name="group_list"),
    path("manage/groups/crud/", RedirectView.as_view(url="/users/manage/groups/", permanent=False)),
    path("manage/groups/crud/", include(views.BusinessGroupViewSet().urls)),

    # Project Directions
    path("manage/project-directions/", views.ProjectDirectionList.as_view(), name="project_direction_list"),
    path("manage/project-directions/crud/", RedirectView.as_view(url="/users/manage/project-directions/", permanent=False)),
    path("manage/project-directions/crud/", include(views.ProjectDirectionViewSet().urls)),

    # Business Directions
    path("manage/business-directions/", views.BusinessDirectionList.as_view(), name="business_direction_list"),
    path("manage/business-directions/crud/", RedirectView.as_view(url="/users/manage/business-directions/", permanent=False)),
    path("manage/business-directions/crud/", include(views.BusinessDirectionViewSet().urls)),
]
