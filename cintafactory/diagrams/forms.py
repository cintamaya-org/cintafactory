from django import forms

from .models import Diagram
from .validation import sanitize_diagram_title


class DiagramForm(forms.ModelForm):
    class Meta:
        model = Diagram
        fields = ["title"]

    def clean_title(self):
        title = self.cleaned_data.get("title")
        return sanitize_diagram_title(title)
