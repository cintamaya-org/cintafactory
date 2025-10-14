from django.urls import include, path
from .views import MyDATList, DATViewSet

app_name = "dat"

urlpatterns = [
    # Material list page "My DAT"
    path("my/", MyDATList.as_view(), name="my_list"),

    # Material CRUD endpoints (same pattern as users: ".../crud/")
    path("manage/dats/crud/", include(DATViewSet().urls)),
]
