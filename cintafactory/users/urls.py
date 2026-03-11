from django.urls import include, path
from django.views import generic
from django.views.generic import RedirectView
from . import views

app_name = "users"

urlpatterns = [
    path("", RedirectView.as_view(url="manage/users/", permanent=False), name="index"),

    # Roles — list (ListView) and CRUD (ModelViewSet)
    path("manage/roles/", views.RoleList.as_view(), name="role_list"),
    path("manage/roles/<uuid:pk>/", views.RoleDetail.as_view(), name="role_detail"),
    path("manage/roles/crud/", include(views.RoleViewSet().urls)),

    # Users — list (ListView) and CRUD (ModelViewSet)
    path("manage/users/", views.UserList.as_view(), name="user_list"),
    path("manage/users/<uuid:pk>/", views.UserDetail.as_view(), name="user_detail"),
    path("manage/users/crud/", include(views.UserViewSet().urls)),

    # Groups — list and CRUD
    path("manage/groups/", views.BusinessGroupList.as_view(), name="group_list"),
    path("manage/groups/<uuid:pk>/", views.BusinessGroupDetail.as_view(), name="group_detail"),
    path("manage/groups/crud/", include(views.BusinessGroupViewSet().urls)),

    # Technical directions
    path("manage/technical-directions/", views.TechnicalDirectionList.as_view(), name="technical_direction_list"),
    path("manage/technical-directions/crud/", include(views.TechnicalDirectionViewSet().urls)),

    # Business Directions
    path("manage/business-directions/", views.BusinessDirectionList.as_view(), name="business_direction_list"),
    path("manage/business-directions/crud/", include(views.BusinessDirectionViewSet().urls)),
]
