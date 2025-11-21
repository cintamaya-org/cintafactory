from django import forms

from .models import BusinessDirection, BusinessGroup, TechnicalDirection, Role, User


class RoleSelect(forms.Select):
    """
    Inject metadata on each option so the UI can toggle roles per direction.
    """

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        role = getattr(value, "instance", None)
        if role is None and isinstance(value, Role):
            role = value
        if role is not None and option["value"]:
            option_attrs = option.setdefault("attrs", {})
            if role.technical_direction_id:
                option_attrs["data-direction"] = str(role.technical_direction_id)
            if role.is_admin_role:
                option_attrs["data-role-admin"] = "1"
        return option


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
            "business_group",
            "is_active",
            "is_staff",
            "is_superuser",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        role_field = self.fields.get("role")
        if role_field:
            role_field.queryset = Role.objects.select_related("technical_direction").order_by("name")
            role_field.widget = RoleSelect(attrs={"data-role-selector": "1"})
            role_field.help_text = (
                "Le rôle doit appartenir à la même direction technique que le groupe métier sélectionné."
            )
            role_field.required = True

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        business_group = cleaned_data.get("business_group")
        role = cleaned_data.get("role")

        if role and business_group:
            group_direction = getattr(business_group, "direction", None)
            if not role.technical_direction_id:
                self.add_error(
                    "role",
                    "Ce rôle n'est pas configuré avec une direction technique. Merci de le mettre à jour.",
                )
            elif group_direction and role.technical_direction_id != group_direction.id:
                self.add_error(
                    "role",
                    (
                        "Ce rôle est rattaché à la direction technique "
                        f"« {role.technical_direction.name} ». Merci d'ajuster votre sélection."
                    ),
                )

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


class BusinessGroupForm(forms.ModelForm):
    class Meta:
        model = BusinessGroup
        fields = ["name", "direction", "responsible", "business_direction"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        business_direction = self.fields.get("business_direction")
        if business_direction:
            business_direction.required = False
            business_direction.label = "Direction métier"
            business_direction.help_text = "Associer au plus un groupe par direction technique."
            business_direction.queryset = business_direction.queryset.order_by("name")


class TechnicalDirectionForm(forms.ModelForm):
    class Meta:
        model = TechnicalDirection
        fields = ["name", "slug"]


class BusinessDirectionForm(forms.ModelForm):
    class Meta:
        model = BusinessDirection
        fields = ["name", "slug"]


class RoleForm(forms.ModelForm):
    class Meta:
        model = Role
        fields = ["name", "slug", "technical_direction", "is_admin_role"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        technical_direction = self.fields.get("technical_direction")
        if technical_direction:
            technical_direction.queryset = technical_direction.queryset.order_by("name")
            technical_direction.help_text = "Direction technique propriétaire de ce rôle."
        is_admin = self.fields.get("is_admin_role")
        if is_admin:
            is_admin.help_text = "Cochez pour les rôles disposant de privilèges administrateur."

    def clean(self):
        cleaned_data = super().clean()
        technical_direction = cleaned_data.get("technical_direction")
        if not technical_direction:
            self.add_error("technical_direction", "La direction technique est obligatoire.")
        return cleaned_data
