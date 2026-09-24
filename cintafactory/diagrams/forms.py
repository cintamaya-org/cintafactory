# SPDX-FileCopyrightText: 2026 Cintamaya <contact@cintamaya.com>
# SPDX-FileCopyrightText: 2026 Baptiste COQUELET <github.com/BaptisteCoquelet>
# SPDX-License-Identifier: AGPL-3.0-only

from django import forms

from .models import DrawIODiagram
from .validation import sanitize_diagram_title


class DiagramForm(forms.ModelForm):
    class Meta:
        model = DrawIODiagram
        fields = ["title"]

    def clean_title(self):
        title = (self.cleaned_data.get("title") or "").strip()
        if not title:
            raise forms.ValidationError("Le titre du diagramme est obligatoire.")
        return sanitize_diagram_title(title)
