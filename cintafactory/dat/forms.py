from django import forms
from .models import DAT, DATStatus

class DATForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        instance = super().save(commit=False)
        if not instance.pk:
            # on create: set creator + force Draft
            if self.user is not None and not instance.created_by_id:
                instance.created_by = self.user
            instance.status = DATStatus.DRAFT
        if commit:
            instance.save()
        return instance

    class Meta:
        model = DAT
        fields = ["title", "project_name"]  # don't expose status/created_by on the form
