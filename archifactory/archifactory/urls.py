"""
URL configuration for archifactory project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from django.urls import include
from django.views.generic.base import RedirectView
from viewflow.contrib.auth import AuthViewset
from viewflow.urls import Application, Site, ModelViewset
from viewflow.workflow.flow import FlowAppViewset
from bibliotheque.flows import DATFlow

site = Site(title="ACME Corp", viewsets=[
    Application(
        title='Sample App', icon='people', app_name='sample', viewsets=[
            FlowAppViewset(DATFlow, icon="assignment"),
        ]
    ),
])

urlpatterns = [
    path('admin/', admin.site.urls),
    # path('bibliotheque/', include('bibliotheque.urls')),
    path('', RedirectView.as_view(url='bibliotheque/', permanent=True)),
    path('accounts/', AuthViewset(with_profile_view=False).urls),
    path('test/', site.urls),
]
