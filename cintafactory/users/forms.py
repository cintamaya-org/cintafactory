from django import forms

from .models import User


class UserForm(forms.ModelForm):
    password1 = forms.CharField(
        label="Mot de passe",
        widget=forms.PasswordInput,
        required=False,
        help_text="Laisser vide pour générer un compte sans mot de passe initial.",
    )
    password2 = forms.CharField(
        label="Confirmer le mot de passe",
        widget=forms.PasswordInput,
        required=False,
    )

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "first_name",
            "last_name",
            "role",
            "architect_referent",
            "is_active",
            "is_staff",
            "is_superuser",
        ]

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")

        if password1 or password2:
            if not password1:
                self.add_error("password1", "Veuillez renseigner un mot de passe.")
            if not password2:
                self.add_error("password2", "Veuillez confirmer le mot de passe.")
            if password1 and password2 and password1 != password2:
                self.add_error("password2", "Les mots de passe ne correspondent pas.")

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get("password1") or ""

        if password:
            user.set_password(password)
        elif not user.password:
            # Keep behaviour for accounts created without a password
            user.set_unusable_password()

        if commit:
            user.save()
            self.save_m2m()

        return user
