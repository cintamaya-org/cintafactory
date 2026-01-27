from django.urls import include, path
from rest_framework.routers import DefaultRouter

from dat.api import ApplicationViewSet, DATViewSet
from users.api import BusinessGroupViewSet, UserViewSet

router = DefaultRouter()
router.register("users", UserViewSet, basename="user")
router.register("groups", BusinessGroupViewSet, basename="business-group")
router.register("applications", ApplicationViewSet, basename="application")
router.register("dats", DATViewSet, basename="dat")

urlpatterns = [
    path("auth/", include("rest_framework.urls")),
    path("", include(router.urls)),
]
