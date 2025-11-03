from django import forms
from django.urls import reverse_lazy
from django.utils.safestring import mark_safe

from .models import DAT, DATStatus


class DATForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        if "application" in self.fields:
            refresh_url = reverse_lazy("dat:application_options")
            self.fields["application"].help_text = mark_safe(
                '<div class="application-field-actions">'
                '<a class="btn waves-effect waves-light cinta-btn-primary" '
                'href="/dat/manage/applications/crud/add/" target="_blank" rel="noopener">'
                '<i class="material-icons left" aria-hidden="true">add_circle</i>Créer une application</a>'
                f'<button type="button" '
                f'class="btn waves-effect waves-light cinta-btn-primary application-refresh-btn" '
                f'data-refresh-url="{refresh_url}">'
                '<i class="material-icons left" aria-hidden="true">refresh</i>Actualiser la liste</button>'
                "</div>"
            )
        if "owner" in self.fields:
            if not self.instance.pk:
                # During creation, show owner as read-only and avoid user selection
                self.fields["owner"].required = False
                self.fields["owner"].disabled = True
                if self.user is not None:
                    self.initial["owner"] = self.user
            else:
                # Allow editing owner later if needed
                self.fields["owner"].disabled = False

    def save(self, commit=True):
        instance = super().save(commit=False)
        if self.user is not None:
            instance._history_actor = self.user  # type: ignore[attr-defined]
        if not instance.pk:
            # on create: set creator + force start step
            if self.user is not None and not getattr(instance, "created_by_id", None):
                instance.created_by = self.user
            if self.user is not None:
                instance.owner = self.user
            instance.status = DATStatus.DEMANDE_INITIALE
        if commit:
            instance.save()
        return instance

    class Meta:
        model = DAT
        fields = ["reference", "title", "application", "description", "status", "owner"]
