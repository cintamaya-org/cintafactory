from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models import Q
from django.db.utils import OperationalError, ProgrammingError
from django.core.exceptions import ValidationError


def _get_default_group_responsible():
    User = get_user_model()
    try:
        user = User.objects.filter(is_superuser=True).order_by("id").first()
        if not user:
            user = User.objects.order_by("id").first()
    except (ProgrammingError, OperationalError):
        user = None
    return user


def _get_default_role_for_group(group=None):
    try:
        if group and group.direction_id:
            return Role.objects.filter(technical_direction=group.direction).order_by("id").first()
        return Role.objects.order_by("id").first()
    except (ProgrammingError, OperationalError):
        return None


class TechnicalDirection(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)

    class Meta:
        db_table = "TECHNICAL_DIRECTION"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def _generate_default_group_name(self):
        base_name = f"{self.name} - Groupe par défaut"
        try:
            existing = BusinessGroup.objects.filter(name__startswith=base_name)
        except (ProgrammingError, OperationalError):
            return base_name
        if not existing.filter(name=base_name).exists():
            return base_name
        counter = 2
        candidate = f"{base_name} {counter}"
        while existing.filter(name=candidate).exists():
            counter += 1
            candidate = f"{base_name} {counter}"
        return candidate

    def ensure_default_group(self):
        try:
            has_default = self.groups.filter(is_default=True).exists()
        except (ProgrammingError, OperationalError):
            return
        if has_default:
            return
        responsible = _get_default_group_responsible()
        if not responsible:
            return
        BusinessGroup.objects.create(
            name=self._generate_default_group_name(),
            direction=self,
            responsible=responsible,
            is_default=True,
        )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.ensure_default_group()


class BusinessDirection(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True)

    class Meta:
        db_table = "BUSINESS_METIER_DIRECTION"
        ordering = ["name"]

    def __str__(self):
        return self.name


class BusinessGroup(models.Model):
    name = models.CharField(max_length=100, unique=True)
    direction = models.ForeignKey(
        TechnicalDirection,
        on_delete=models.PROTECT,
        related_name="groups",
    )
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="managed_groups",
    )
    is_default = models.BooleanField(default=False)
    business_direction = models.ForeignKey(
        BusinessDirection,
        on_delete=models.PROTECT,
        related_name="project_groups",
        null=True,
        blank=True,
        help_text="Direction métier associée à ce groupe.",
    )

    class Meta:
        db_table = "BUSINESS_GROUP"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["direction"],
                condition=Q(is_default=True),
                name="unique_default_group_per_direction",
            ),
            models.UniqueConstraint(
                fields=["business_direction", "direction"],
                condition=Q(business_direction__isnull=False),
                name="unique_business_direction_group_per_technical_direction",
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def member_count(self):
        cached = getattr(self, "user_total", None)
        if cached is not None:
            return cached
        return self.users.count()


class Role(models.Model):
    name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)
    technical_direction = models.ForeignKey(
        TechnicalDirection,
        on_delete=models.PROTECT,
        related_name="roles",
        null=True,
        blank=True,
        help_text="Direction technique associée à ce rôle.",
    )
    is_admin_role = models.BooleanField(
        default=False,
        help_text="Les rôles administrateurs ne sont pas rattachés à une direction technique.",
    )

    class Meta:
        db_table = "USER_ROLE"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        if not self.technical_direction_id:
            raise ValidationError({"technical_direction": "La direction technique est obligatoire pour chaque rôle."})

class User(AbstractUser):
    role = models.ForeignKey(
        Role, on_delete=models.PROTECT, null=True, blank=True, related_name="users"
    )
    business_group = models.ForeignKey(
        BusinessGroup,
        on_delete=models.PROTECT,
        related_name="users",
        help_text="Groupe métier auquel appartient l'utilisateur.",
    )

    def is_role(self, slug: str) -> bool:
        return bool(self.role and self.role.slug == slug)

    def clean(self):
        super().clean()

        try:
            groups_exist = BusinessGroup.objects.exists()
        except (ProgrammingError, OperationalError):
            groups_exist = False

        if not self.business_group_id and groups_exist:
            raise ValidationError({"business_group": "Chaque utilisateur doit appartenir à un groupe."})

        try:
            roles_exist = Role.objects.exists()
        except (ProgrammingError, OperationalError):
            roles_exist = False

        if not self.role_id and roles_exist:
            raise ValidationError({"role": "Chaque utilisateur doit avoir un rôle."})

        if self.role_id and self.business_group_id:
            role = getattr(self, "role", None)
            if role and role.pk != self.role_id:
                role = None
            if role is None:
                role = Role.objects.filter(pk=self.role_id).only("technical_direction_id").first()
            group = getattr(self, "business_group", None)
            if group and group.pk != self.business_group_id:
                group = None
            if group is None:
                group = BusinessGroup.objects.filter(pk=self.business_group_id).only("direction_id").first()
            role_direction_id = getattr(role, "technical_direction_id", None) if role else None
            group_direction_id = getattr(group, "direction_id", None) if group else None
            if role_direction_id and group_direction_id and role_direction_id != group_direction_id:
                raise ValidationError(
                    {"role": "Le rôle sélectionné doit appartenir à la même direction technique que le groupe métier."}
                )

    def save(self, *args, **kwargs):
        if not self.password:
            # Ensure new users created without an explicit password get an unusable one
            self.set_unusable_password()
        if not self.business_group_id:
            try:
                default_group = BusinessGroup.objects.order_by("id").first()
            except (ProgrammingError, OperationalError):
                default_group = None
            if default_group and not self.business_group_id:
                self.business_group = default_group
        if not self.role_id:
            group = getattr(self, "business_group", None)
            if not group and self.business_group_id:
                try:
                    group = BusinessGroup.objects.select_related("direction").filter(pk=self.business_group_id).first()
                except (ProgrammingError, OperationalError):
                    group = None
            default_role = _get_default_role_for_group(group)
            if default_role and not self.role_id:
                self.role = default_role
        self.full_clean()
        super().save(*args, **kwargs)
