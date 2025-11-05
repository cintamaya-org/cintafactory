from django.contrib.auth.forms import PasswordChangeForm


class AccountPasswordChangeForm(PasswordChangeForm):
    """Password change form with French-facing labels and messages."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = "Ancien mot de passe"
        self.fields["old_password"].help_text = ""
        self.fields["new_password1"].label = "Nouveau mot de passe"
        self.fields["new_password1"].help_text = (
            "Utilisez au moins 8 caracteres et evitez les mots de passe courants."
        )
        self.fields["new_password2"].label = "Confirmation du mot de passe"
        self.fields["new_password2"].help_text = "Saisissez de nouveau le nouveau mot de passe."
