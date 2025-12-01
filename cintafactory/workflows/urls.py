from __future__ import annotations

from django.urls import path

from .views import (
    MyTasksBoardView,
    WorkflowBoardView,
    WorkflowNotificationsView,
    WorkflowOverviewView,
)

app_name = "workflows"

urlpatterns = [
    path("", WorkflowOverviewView.as_view(), name="index"),
    path("overview/", WorkflowOverviewView.as_view(), name="overview"),
    path("board/", WorkflowBoardView.as_view(), name="board"),
    path("mes-taches/", MyTasksBoardView.as_view(), name="my_tasks"),
    path("notifications/", WorkflowNotificationsView.as_view(), name="notifications"),
]
