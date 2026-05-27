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
