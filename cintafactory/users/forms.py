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


class BusinessGroupSelect(forms.Select):
    """
    Expose the technical direction on each option to align roles and groupes côté UI.
    """

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        group = getattr(value, "instance", None)
        if group is None and isinstance(value, BusinessGroup):
            group = value
        if group is not None and option["value"]:
            option_attrs = option.setdefault("attrs", {})
            if group.direction_id:
                option_attrs["data-direction"] = str(group.direction_id)
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
                "Si le rôle est rattaché à une direction technique, l'utilisateur doit appartenir à un groupe de cette direction."
            )
            role_field.required = True
        business_group = self.fields.get("business_group")
        if business_group:
            business_group.required = False
            business_group.queryset = business_group.queryset.select_related("direction").order_by("name")
            business_group.widget = BusinessGroupSelect(attrs={"data-group-selector": "1"})
            business_group.help_text = (
                "Sélectionnez un groupe uniquement si le rôle choisi est associé à une direction technique."
            )

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        business_group = cleaned_data.get("business_group")
        role = cleaned_data.get("role")

        if role and role.technical_direction_id:
            if not business_group:
                self.add_error(
                    "business_group",
                    "Ce rôle requiert un groupe rattaché à sa direction technique.",
                )
            elif business_group.direction_id != role.technical_direction_id:
                self.add_error(
                    "role",
                    (
                        "Ce rôle est rattaché à la direction technique "
                        f"« {role.technical_direction.name} ». Merci d'ajuster votre sélection."
                    ),
                )
        elif business_group:
            self.add_error(
                "business_group",
                "Les rôles sans direction technique ne peuvent pas être associés à un groupe.",
            )
        elif not role:
            self.add_error("role", "Chaque utilisateur doit avoir un rôle.")

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
            technical_direction.help_text = (
                "Direction technique propriétaire de ce rôle. Laissez vide pour un rôle sans rattachement de groupe."
            )
        is_admin = self.fields.get("is_admin_role")
        if is_admin:
            is_admin.help_text = "Cochez pour les rôles disposant de privilèges administrateur."
