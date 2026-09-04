from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class ConfigurationAccessTests(TestCase):
    def setUp(self):
        self.UserModel = get_user_model()
        self.superuser = self.UserModel.objects.create_superuser(
            username="config-superadmin",
            email="config-superadmin@example.com",
            password="pwd",
        )
        self.standard_user = self.UserModel.objects.create_user(
            username="config-user",
            email="config-user@example.com",
            password="pwd",
        )

    def test_superuser_can_access_configuration(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("configuration:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Configuration")

    def test_non_superuser_is_forbidden(self):
        self.client.force_login(self.standard_user)
        response = self.client.get(reverse("configuration:index"))
        self.assertEqual(response.status_code, 403)
