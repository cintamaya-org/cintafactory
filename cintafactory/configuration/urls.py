# SPDX-FileCopyrightText: 2026 Cintamaya <contact@cintamaya.com>
# SPDX-FileCopyrightText: 2026 Baptiste COQUELET <github.com/BaptisteCoquelet>
# SPDX-License-Identifier: AGPL-3.0-only

from django.urls import path

from . import views

app_name = "configuration"

urlpatterns = [
    path("", views.ConfigurationHomeView.as_view(), name="index"),
]
