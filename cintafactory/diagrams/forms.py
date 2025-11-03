from django import forms

from .models import Diagram


class DiagramForm(forms.ModelForm):
    class Meta:
        model = Diagram
        fields = ["title"]
