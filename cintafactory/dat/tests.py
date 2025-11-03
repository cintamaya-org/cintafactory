from django.contrib.auth import get_user_model
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from users.models import Role

from .models import Application, DAT, DATParticipant, DATStatus, DATHistoryAction

class SmokeTest(TestCase):
    def test_import(self):
        self.assertTrue(DAT)

class DATApplicationRelationTest(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create(username="owner")
        self.application = Application.objects.create(code="app-code", name="App Name")

    def test_dat_links_to_single_application(self):
        dat = DAT.objects.create(
            reference="DAT-001",
            title="Integration Test",
            application=self.application,
            status=DATStatus.DEMANDE_INITIALE,
            owner=self.user,
        )
        self.assertEqual(dat.application, self.application)
        self.assertIn(dat, self.application.dats.all())

    def test_protects_application_from_deletion(self):
        dat = DAT.objects.create(
            reference="DAT-002",
            title="Deletion Test",
            application=self.application,
            status=DATStatus.DEMANDE_INITIALE,
        )
        with self.assertRaisesMessage(ProtectedError, "protected"):
            self.application.delete()
        dat.delete()
        self.application.delete()
        self.assertFalse(Application.objects.filter(pk=self.application.pk).exists())

class ApplicationOptionsViewTest(TestCase):
    def setUp(self) -> None:
        self.url = reverse("dat:application_options")
        self.staff = get_user_model().objects.create_user(
            username="manager",
            password="pwd",
            is_staff=True,
        )
        self.role_porteur = Role.objects.create(name="Porteur de la demande", slug="porteur-demande")
        self.porteur = get_user_model().objects.create_user(
            username="porteur",
            password="pwd",
        )
        self.porteur.role = self.role_porteur
        self.porteur.save()
        Application.objects.create(code="app-1", name="App One")
        Application.objects.create(code="app-2", name="App Two")

    def test_requires_management_rights(self):
        user = get_user_model().objects.create_user(username="regular", password="pwd")
        self.client.force_login(user)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_porteur_can_access(self):
        self.client.force_login(self.porteur)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_returns_sorted_options(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("options", payload)
        labels = [option["label"] for option in payload["options"]]
        self.assertEqual(labels, sorted(labels))


class DatCreationPermissionTest(TestCase):
    def setUp(self) -> None:
        self.dat_add_url = "/dat/manage/dats/crud/add/"
        self.application_add_url = "/dat/manage/applications/crud/add/"
        self.role_porteur = Role.objects.create(name="Porteur de la demande", slug="porteur-demande")
        self.porteur = get_user_model().objects.create_user(
            username="porteur-creator",
            password="pwd",
        )
        self.porteur.role = self.role_porteur
        self.porteur.save(update_fields=["role"])
        self.staff = get_user_model().objects.create_user(
            username="staff-editor",
            password="pwd",
            is_staff=True,
        )

    def test_staff_cannot_access_dat_creation(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.dat_add_url)
        self.assertEqual(response.status_code, 403)

    def test_porteur_can_access_dat_creation(self):
        self.client.force_login(self.porteur)
        response = self.client.get(self.dat_add_url)
        self.assertEqual(response.status_code, 200)

    def test_staff_cannot_access_application_creation(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.application_add_url)
        self.assertEqual(response.status_code, 403)

    def test_porteur_can_access_application_creation(self):
        self.client.force_login(self.porteur)
        response = self.client.get(self.application_add_url)
        self.assertEqual(response.status_code, 200)


class DatAdminListViewTest(TestCase):
    def setUp(self) -> None:
        self.url = reverse("dat:admin_list")
        self.staff = get_user_model().objects.create_user(
            username="staff-user",
            password="pwd",
            is_staff=True,
        )
        self.regular = get_user_model().objects.create_user(
            username="regular-user",
            password="pwd",
        )
        self.application = Application.objects.create(code="app-admin", name="Application Admin")
        DAT.objects.create(
            reference="DAT-ADMIN-1",
            title="Admin DAT 1",
            application=self.application,
            status=DATStatus.DEMANDE_INITIALE,
            owner=self.staff,
        )
        DAT.objects.create(
            reference="DAT-ADMIN-2",
            title="Admin DAT 2",
            application=self.application,
            status=DATStatus.INSTRUCTION_ARCHITECTURE,
            owner=self.regular,
        )

    def test_requires_management_rights(self):
        self.client.force_login(self.regular)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_staff_sees_all_dats(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("DAT-ADMIN-1", content)
        self.assertIn("DAT-ADMIN-2", content)


class DatVisibilityRestrictionTest(TestCase):
    def setUp(self) -> None:
        self.owner = get_user_model().objects.create_user(username="owner-user", password="pwd")
        self.other = get_user_model().objects.create_user(username="other-user", password="pwd")
        self.admin = get_user_model().objects.create_user(
            username="admin-user",
            password="pwd",
            is_staff=True,
        )
        self.application = Application.objects.create(code="app-vis", name="Visibility App")
        self.dat = DAT.objects.create(
            reference="DAT-VIS-1",
            title="Visibility DAT",
            application=self.application,
            status=DATStatus.DEMANDE_INITIALE,
            owner=self.owner,
        )

    def test_owner_can_view_dat_detail(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("dat:dat_detail", args=[self.dat.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visibility DAT")

    def test_unassigned_user_cannot_view_dat_detail(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse("dat:dat_detail", args=[self.dat.pk]))
        self.assertEqual(response.status_code, 404)

    def test_participant_can_view_dat_detail(self):
        role = self._assign_porteur_role(self.other)
        DATParticipant.objects.create(dat=self.dat, role=role, user=self.other)
        self.client.force_login(self.other)
        response = self.client.get(reverse("dat:dat_detail", args=[self.dat.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visibility DAT")

    def test_admin_can_view_any_dat_detail(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dat:dat_detail", args=[self.dat.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visibility DAT")

    def test_owner_can_view_my_detail_page(self):
        self.client.force_login(self.owner)
        response = self.client.get(reverse("dat:my_detail", args=[self.dat.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visibility DAT")

    def test_unassigned_user_cannot_view_my_detail_page(self):
        self.client.force_login(self.other)
        response = self.client.get(reverse("dat:my_detail", args=[self.dat.pk]))
        self.assertEqual(response.status_code, 404)

    def test_participant_can_view_my_detail_page(self):
        role = self._assign_porteur_role(self.other)
        DATParticipant.objects.create(dat=self.dat, role=role, user=self.other)
        self.client.force_login(self.other)
        response = self.client.get(reverse("dat:my_detail", args=[self.dat.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visibility DAT")

    def test_admin_can_view_my_detail_page(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dat:my_detail", args=[self.dat.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visibility DAT")

    def _assign_porteur_role(self, user):
        role, _ = Role.objects.get_or_create(
            slug="porteur-demande",
            defaults={"name": "Porteur de la demande"},
        )
        user.role = role
        user.save(update_fields=["role"])
        return role

    def test_owner_with_role_can_advance_to_next_status(self):
        self._assign_porteur_role(self.owner)
        self.client.force_login(self.owner)
        response = self.client.post(reverse("dat:my_advance", args=[self.dat.pk]))
        self.assertRedirects(response, reverse("dat:my_detail", args=[self.dat.pk]))
        self.dat.refresh_from_db()
        self.assertEqual(self.dat.status, DATStatus.VALIDATION_REFERENT)

    def test_owner_without_role_cannot_advance(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("dat:my_advance", args=[self.dat.pk]))
        self.assertEqual(response.status_code, 403)
        self.dat.refresh_from_db()
        self.assertEqual(self.dat.status, DATStatus.DEMANDE_INITIALE)

    def test_unassigned_user_cannot_advance(self):
        self._assign_porteur_role(self.other)
        self.client.force_login(self.other)
        response = self.client.post(reverse("dat:my_advance", args=[self.dat.pk]))
        self.assertEqual(response.status_code, 404)
        self.dat.refresh_from_db()
        self.assertEqual(self.dat.status, DATStatus.DEMANDE_INITIALE)

    def test_button_visibility_depends_on_permissions(self):
        detail_url = reverse("dat:my_detail", args=[self.dat.pk])

        self.client.force_login(self.owner)
        response = self.client.get(detail_url)
        self.assertNotContains(response, "Passer à l'étape suivante")

        self._assign_porteur_role(self.owner)
        response_with_role = self.client.get(detail_url)
        self.assertContains(response_with_role, "Passer à l'étape suivante")

    def test_list_only_shows_assigned_dats(self):
        DAT.objects.create(
            reference="DAT-VIS-2",
            title="Other DAT",
            application=self.application,
            status=DATStatus.INSTRUCTION_ARCHITECTURE,
            owner=self.other,
        )
        shared_dat = DAT.objects.create(
            reference="DAT-VIS-3",
            title="Shared DAT",
            application=self.application,
            status=DATStatus.VALIDATION_REFERENT,
            owner=self.other,
        )
        role = self._assign_porteur_role(self.owner)
        DATParticipant.objects.create(dat=shared_dat, role=role, user=self.owner)

        self.client.force_login(self.owner)
        response = self.client.get(reverse("dat:my_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "DAT-VIS-1")
        self.assertContains(response, "DAT-VIS-3")
        self.assertNotContains(response, "DAT-VIS-2")

        self.client.force_login(self.other)
        response_other = self.client.get(reverse("dat:my_list"))
        self.assertEqual(response_other.status_code, 200)
        self.assertContains(response_other, "DAT-VIS-2")
        self.assertNotContains(response_other, "DAT-VIS-1")
        self.assertContains(response_other, "DAT-VIS-3")

class ApplicationModelFormattingTest(TestCase):
    def test_formatted_dates(self):
        application = Application.objects.create(code="format-app", name="Format App")
        formatted_created = application.formatted_created_at()
        formatted_updated = application.formatted_updated_at()
        self.assertIn("/", formatted_created)
        self.assertIn("h", formatted_created)
        self.assertIn("/", formatted_updated)
        self.assertIn("h", formatted_updated)


class DatHistoryTest(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(username="history-user")
        self.manager = get_user_model().objects.create_user(
            username="history-manager",
            is_staff=True,
        )
        self.application = Application.objects.create(code="hist-app", name="History App")

    def _create_dat(self) -> DAT:
        dat = DAT(
            reference="DAT-HIST-1",
            title="History Tracking",
            application=self.application,
            status=DATStatus.DEMANDE_INITIALE,
        )
        dat._history_actor = self.user  # type: ignore[attr-defined]
        dat.save()
        return dat

    def test_history_entry_created_on_creation(self):
        dat = self._create_dat()
        entries = dat.history_entries.all()
        self.assertEqual(entries.count(), 1)
        entry = entries.first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.action, DATHistoryAction.CREATED)
        self.assertEqual(entry.status_after, DATStatus.DEMANDE_INITIALE)
        self.assertEqual(entry.performed_by, self.user)
        self.assertEqual(entry.actor_name(), self.user.username)

    def test_status_change_records_history_entry(self):
        dat = self._create_dat()
        dat.status = DATStatus.VALIDATION_REFERENT
        dat._history_actor = self.manager  # type: ignore[attr-defined]
        dat.save()
        status_entries = dat.history_entries.filter(action=DATHistoryAction.STATUS_CHANGED)
        self.assertEqual(status_entries.count(), 1)
        entry = status_entries.first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.status_before, DATStatus.DEMANDE_INITIALE)
        self.assertEqual(entry.status_after, DATStatus.VALIDATION_REFERENT)
        self.assertEqual(entry.details.get("from"), DATStatus.DEMANDE_INITIALE.label)
        self.assertEqual(entry.details.get("to"), DATStatus.VALIDATION_REFERENT.label)
        self.assertEqual(entry.performed_by, self.manager)
        self.assertEqual(entry.actor_name(), self.manager.username)
        self.assertEqual(
            dat.history_entries.filter(action=DATHistoryAction.UPDATED).count(),
            0,
        )

    def test_detail_view_displays_history(self):
        dat = self._create_dat()
        dat.status = DATStatus.VALIDATION_REFERENT
        dat._history_actor = self.manager  # type: ignore[attr-defined]
        dat.save()
        self.client.force_login(self.manager)
        url = reverse("dat:dat_detail", args=[dat.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Historique du dossier", content)
        self.assertIn(self.manager.username, content)
        self.assertIn(DATStatus.VALIDATION_REFERENT.label, content)
