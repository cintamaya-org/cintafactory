from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError

class Role(models.Model):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)

    class Meta:
        db_table = "USER_ROLE"
        ordering = ["name"]

    def __str__(self):
        return self.name

class User(AbstractUser):
    role = models.ForeignKey(
        Role, on_delete=models.PROTECT, null=True, blank=True, related_name="users"
    )
    architect_referent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="technical_architects",
        limit_choices_to={"role__slug": "architecte-referent"},
        help_text="Referent de rattachement pour les architectes techniques.",
    )

    def is_role(self, slug: str) -> bool:
        return bool(self.role and self.role.slug == slug)

    def clean(self):
        super().clean()

        slug = self.role.slug if self.role else None

        if slug == "architecte-technique" and not self.architect_referent_id:
            raise ValidationError(
                {"architect_referent": "Un architecte technique doit avoir un referent."}
            )

        if slug == "architecte-referent" and self.architect_referent_id:
            raise ValidationError(
                {"architect_referent": "Un architecte referent ne peut pas avoir de referent."}
            )

    def save(self, *args, **kwargs):
        if not self.password:
            # Ensure new users created without an explicit password get an unusable one
            self.set_unusable_password()
        self.full_clean()
        super().save(*args, **kwargs)
