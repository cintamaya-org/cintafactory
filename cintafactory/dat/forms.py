from django import forms

from .models import DAT, DATStatus


class DATForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        instance = super().save(commit=False)
        if not instance.pk:
            # on create: set creator + force start step
            if self.user is not None and not getattr(instance, "created_by_id", None):
                instance.created_by = self.user
            instance.status = DATStatus.BESOIN_DAL
        if commit:
            instance.save()
        return instance

    class Meta:
        model = DAT
        fields = ["title", "project_name"]  # don't expose status/created_by on the form
