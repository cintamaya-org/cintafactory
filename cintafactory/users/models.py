from django.db import models
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

    def is_role(self, slug: str) -> bool:
        return bool(self.role and self.role.slug == slug)
