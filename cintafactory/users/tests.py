from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import BusinessDirection, BusinessGroup, TechnicalDirection, Role


class UserDetailViewTests(TestCase):
    def setUp(self):
        self.UserModel = get_user_model()
        self.superuser = self.UserModel.objects.create_superuser(
            username="super-admin",
            email="admin@example.com",
            password="pwd",
        )
        self.tech_direction = TechnicalDirection.objects.create(name="Tech Dir", slug="tech-dir-detail")
        self.business_direction = BusinessDirection.objects.create(name="Direction Métier", slug="business-dir-detail")
        self.group = BusinessGroup.objects.create(
            name="Groupe Détail",
            direction=self.tech_direction,
            responsible=self.superuser,
            business_direction=self.business_direction,
        )
        self.superuser.business_group = self.group
        self.superuser.save(update_fields=["business_group"])
        self.role = Role.objects.create(name="Architecte Détail", slug="architecte-detail", technical_direction=self.tech_direction)
        self.superuser.role = self.role
        self.superuser.save(update_fields=["role"])
        self.target_user = self.UserModel.objects.create_user(
            username="detail-user",
            password="pwd",
            role=self.role,
            business_group=self.group,
        )

    def test_superuser_can_view_user_detail(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("users:user_detail", kwargs={"pk": self.target_user.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Profil utilisateur")
        self.assertContains(response, self.target_user.username)
        self.assertContains(response, self.role.name)

    def test_non_superuser_is_forbidden(self):
        outsider = self.UserModel.objects.create_user(
            username="outsider",
            password="pwd",
            role=self.role,
            business_group=self.group,
        )
        self.client.force_login(outsider)
        response = self.client.get(reverse("users:user_detail", kwargs={"pk": self.target_user.pk}))
        self.assertEqual(response.status_code, 403)


class UserModelConstraintTests(TestCase):
    def setUp(self):
        self.UserModel = get_user_model()
        self.superuser = self.UserModel.objects.create_superuser(
            username="constraint-admin",
            email="constraint-admin@example.com",
            password="pwd",
        )
        self.direction_a = TechnicalDirection.objects.create(name="Direction A", slug="direction-a")
        self.direction_b = TechnicalDirection.objects.create(name="Direction B", slug="direction-b")
        self.role_a = Role.objects.create(name="Role A", slug="role-a", technical_direction=self.direction_a)
        self.role_b = Role.objects.create(name="Role B", slug="role-b", technical_direction=self.direction_b)
        self.role_transverse = Role.objects.create(name="Role Transverse", slug="role-transverse")
        self.group_a = BusinessGroup.objects.create(
            name="Groupe A",
            direction=self.direction_a,
            responsible=self.superuser,
        )
        self.group_b = BusinessGroup.objects.create(
            name="Groupe B",
            direction=self.direction_b,
            responsible=self.superuser,
        )
        self.superuser.business_group = self.group_a
        self.superuser.role = self.role_a
        self.superuser.save(update_fields=["business_group", "role"])

    def test_user_without_role_is_invalid(self):
        user = self.UserModel(
            username="no-role",
            email="no-role@example.com",
            business_group=self.group_a,
        )
        user.set_password("pwd")
        with self.assertRaises(ValidationError):
            user.full_clean()

    def test_user_role_must_match_group_direction(self):
        user = self.UserModel(
            username="direction-mismatch",
            email="mismatch@example.com",
            role=self.role_b,
            business_group=self.group_a,
        )
        user.set_password("pwd")
        with self.assertRaises(ValidationError):
            user.full_clean()

    def test_default_role_is_assigned_when_missing(self):
        user = self.UserModel.objects.create_user(
            username="auto-role",
            password="pwd",
            business_group=self.group_a,
        )
        self.assertEqual(user.business_group, self.group_a)
        self.assertEqual(user.role, self.role_a)

    def test_role_requires_group_when_direction_is_set(self):
        user = self.UserModel(
            username="needs-group",
            email="needs-group@example.com",
            role=self.role_a,
        )
        user.set_password("pwd")
        with self.assertRaises(ValidationError):
            user.full_clean()

    def test_directionless_role_cannot_have_group(self):
        user = self.UserModel(
            username="transverse-grouped",
            email="transverse@example.com",
            role=self.role_transverse,
            business_group=self.group_a,
        )
        user.set_password("pwd")
        with self.assertRaises(ValidationError):
            user.full_clean()
