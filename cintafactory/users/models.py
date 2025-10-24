from django.db import models
from django.db.models import Q
from django.contrib.auth.models import AbstractUser

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

    class Meta(AbstractUser.Meta):
        constraints = [
            models.CheckConstraint(
                check=Q(role__slug="architecte-technique", architect_referent__isnull=False)
                | ~Q(role__slug="architecte-technique"),
                name="architecte_technique_requires_referent",
            ),
            models.CheckConstraint(
                check=~Q(role__slug="architecte-referent", architect_referent__isnull=False),
                name="architecte_referent_cannot_have_referent",
            ),
        ]
