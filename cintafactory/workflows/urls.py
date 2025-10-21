from __future__ import annotations

from django.urls import path

from .views import WorkflowBoardView

app_name = "workflows"

urlpatterns = [
    path("", WorkflowBoardView.as_view(), name="index"),
    path("board/", WorkflowBoardView.as_view(), name="board"),
]
