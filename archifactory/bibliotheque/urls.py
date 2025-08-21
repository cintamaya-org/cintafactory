from django.urls import path
from django.urls import include
from django.views.generic.base import RedirectView

urlpatterns = [
    path('', views.index, name='index'),
    path('persons/', views.PersonListView.as_view(), name='persons'),
]
