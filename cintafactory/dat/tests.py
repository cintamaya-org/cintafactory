import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse

from cintafactory.logging_utils import bind_request_context, clear_request_context

from diagrams.models import Diagram
from users.models import BusinessDirection, BusinessGroup, Role, TechnicalDirection

from .constants import (
    DAT_PORTEUR_ROLE_SLUG,
    DAT_REQUIRED_PARTICIPANT_ROLE_LABELS,
    DAT_REQUIRED_PARTICIPANT_ROLE_SLUGS,
)
from .exporters import DATExportModelBuilder
from .forms import DATForm
from .models import Application, DAT, DATParticipant, DATPart, DATPartEntryType, DATStatus, DATHistoryAction
from .sections import SECTION_STATUS_VALIDATED_VALUE, sync_dat_sections_if_needed
from .tasks import _run_pdf_generation
from workflows.models import UserNotification

def get_default_business_direction():
    direction, _ = BusinessDirection.objects.get_or_create(
        slug="direction-metier-test",
        defaults={"name": "Direction Métier Test"},
    )
    return direction


def get_default_technical_direction():
    direction, _ = TechnicalDirection.objects.get_or_create(
        slug="direction-technique-test",
        defaults={"name": "Direction Technique Test"},
    )
    return direction


def create_role(slug: str, name: str) -> Role:
    return Role.objects.create(name=name, slug=slug, technical_direction=get_default_technical_direction())


def ensure_role(slug: str, name: str) -> Role:
    defaults = {"name": name, "technical_direction": get_default_technical_direction()}
    role, created = Role.objects.get_or_create(slug=slug, defaults=defaults)
    if not created and role.technical_direction_id is None:
        role.technical_direction = defaults["technical_direction"]
        role.save(update_fields=["technical_direction"])
    return role


class SmokeTest(TestCase):
    def test_import(self):
        self.assertTrue(DAT)

class DATApplicationRelationTest(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create(username="owner")
        self.business_direction = get_default_business_direction()
        self.application = Application.objects.create(
            code="app-code",
            name="App Name",
            business_direction=self.business_direction,
        )

    def test_dat_links_to_single_application(self):
        dat = DAT.objects.create(
            reference="DAT-001",
            title="Integration Test",
            application=self.application,
            status=DATStatus.NOUVELLE_DEMANDE,
            owner=self.user,
        )
        self.assertEqual(dat.application, self.application)
        self.assertIn(dat, self.application.dats.all())

    def test_protects_application_from_deletion(self):
        dat = DAT.objects.create(
            reference="DAT-002",
            title="Deletion Test",
            application=self.application,
            status=DATStatus.NOUVELLE_DEMANDE,
        )
        with self.assertRaisesMessage(ProtectedError, "protected"):
            self.application.delete()
        dat.delete()
        self.application.delete()
        self.assertFalse(Application.objects.filter(pk=self.application.pk).exists())

    def test_dat_inherits_application_business_direction(self):
        dat = DAT.objects.create(
            reference="DAT-003",
            title="Direction Test",
            application=self.application,
            status=DATStatus.NOUVELLE_DEMANDE,
            owner=self.user,
        )
        self.assertEqual(dat.business_direction, self.business_direction)

class ApplicationOptionsViewTest(TestCase):
    def setUp(self) -> None:
        self.url = reverse("dat:application_options")
        self.staff = get_user_model().objects.create_user(
            username="manager",
            password="pwd",
            is_staff=True,
        )
        self.role_porteur = create_role("porteur-demande", "Porteur de la demande")
        self.porteur = get_user_model().objects.create_user(
            username="porteur",
            password="pwd",
        )
        self.porteur.role = self.role_porteur
        self.porteur.save()
        direction = get_default_business_direction()
        Application.objects.create(code="app-1", name="App One", business_direction=direction)
        Application.objects.create(code="app-2", name="App Two", business_direction=direction)

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

    def test_skips_applications_without_direction(self):
        Application.objects.create(code="app-3", name="Sans direction", business_direction=None)
        self.client.force_login(self.staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        option_labels = [option["label"] for option in payload["options"]]
        self.assertNotIn("Sans direction", option_labels)


class DatCreationPermissionTest(TestCase):
    def setUp(self) -> None:
        self.dat_add_url = "/dat/manage/dats/crud/add/"
        self.application_add_url = "/dat/manage/applications/crud/add/"
        self.role_porteur = create_role("porteur-demande", "Porteur de la demande")
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
        direction = get_default_business_direction()
        self.application = Application.objects.create(
            code="app-admin",
            name="Application Admin",
            business_direction=direction,
        )
        DAT.objects.create(
            reference="DAT-ADMIN-1",
            title="Admin DAT 1",
            application=self.application,
            status=DATStatus.NOUVELLE_DEMANDE,
            owner=self.staff,
        )
        DAT.objects.create(
            reference="DAT-ADMIN-2",
            title="Admin DAT 2",
            application=self.application,
            status=DATStatus.EN_COURS,
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


class DatImportViewTest(TestCase):
    def setUp(self) -> None:
        self.url = reverse("dat:import")
        self.admin = get_user_model().objects.create_user(
            username="import-admin",
            password="pwd",
            is_staff=True,
        )
        self.regular = get_user_model().objects.create_user(username="import-user", password="pwd")
        self.porteur_role = create_role(DAT_PORTEUR_ROLE_SLUG, "Porteur")
        self.porteur = get_user_model().objects.create_user(username="porteur-import", password="pwd")
        self.porteur.role = self.porteur_role
        self.porteur.save(update_fields=["role"])
        self.business_direction = get_default_business_direction()
        self.application = Application.objects.create(
            code="app-import",
            name="Application Import",
            business_direction=self.business_direction,
        )
        self.sample_part_value = "Architecture importée"

    def _build_payload(self):
        dat = DAT.objects.create(
            reference="DAT-EXPORT-IMPORT",
            title="DAT pour export",
            application=self.application,
            status=DATStatus.NOUVELLE_DEMANDE,
            owner=self.porteur,
        )
        sync_dat_sections_if_needed(dat)
        DATParticipant.objects.create(dat=dat, role=self.porteur_role, user=self.porteur)
        part = (
            dat.sections.get(slug="architecture")
            .sub_sections.get(slug="presentation-generale")
            .parts.get(key="presentation_generale")
        )
        part.update_value(part.prepare_value(self.sample_part_value))
        builder = DATExportModelBuilder()
        payload = builder.build(dat)
        payload["dat"]["reference"] = "DAT-IMPORT-001"
        payload["dat"]["title"] = "DAT importé"
        return payload

    def test_requires_management_rights(self):
        self.client.force_login(self.regular)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_imports_dat_from_json(self):
        payload = self._build_payload()
        upload = SimpleUploadedFile(
            "dat.json",
            json.dumps(payload).encode("utf-8"),
            content_type="application/json",
        )
        self.client.force_login(self.admin)
        response = self.client.post(self.url, {"data_file": upload})
        self.assertEqual(response.status_code, 302)
        imported = DAT.objects.get(reference=payload["dat"]["reference"])
        self.assertEqual(imported.title, payload["dat"]["title"])
        self.assertEqual(imported.application, self.application)
        self.assertEqual(imported.owner, self.porteur)
        participant_qs = imported.participants.filter(role__slug=DAT_PORTEUR_ROLE_SLUG)
        self.assertEqual(participant_qs.count(), 1)
        part = (
            imported.sections.get(slug="architecture")
            .sub_sections.get(slug="presentation-generale")
            .parts.get(key="presentation_generale")
        )
        self.assertEqual(part.value, self.sample_part_value)

    def test_allows_reference_override(self):
        payload = self._build_payload()
        DAT.objects.create(
            reference=payload["dat"]["reference"],
            title="Existing DAT",
            application=self.application,
            status=DATStatus.NOUVELLE_DEMANDE,
            owner=self.porteur,
        )
        upload = SimpleUploadedFile(
            "dat.json",
            json.dumps(payload).encode("utf-8"),
            content_type="application/json",
        )
        override_reference = "DAT-IMPORT-NEW"
        self.client.force_login(self.admin)
        response = self.client.post(
            self.url,
            {"data_file": upload, "reference_override": override_reference},
        )
        self.assertEqual(response.status_code, 302)
        imported = DAT.objects.get(reference=override_reference)
        self.assertEqual(imported.title, payload["dat"]["title"])


class DatVisibilityRestrictionTest(TestCase):
    def setUp(self) -> None:
        self.roles = {}
        for slug, label in DAT_REQUIRED_PARTICIPANT_ROLE_LABELS.items():
            self.roles[slug] = ensure_role(slug, label)
        self.owner = get_user_model().objects.create_user(username="owner-user", password="pwd")
        self.other = get_user_model().objects.create_user(username="other-user", password="pwd")
        self.admin = get_user_model().objects.create_user(
            username="admin-user",
            password="pwd",
            is_staff=True,
        )
        direction = get_default_business_direction()
        self.application = Application.objects.create(
            code="app-vis",
            name="Visibility App",
            business_direction=direction,
        )
        self.dat = DAT.objects.create(
            reference="DAT-VIS-1",
            title="Visibility DAT",
            application=self.application,
            status=DATStatus.NOUVELLE_DEMANDE,
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
        self._bind_participant(self.dat, DAT_PORTEUR_ROLE_SLUG, self.other)
        self.client.force_login(self.other)
        response = self.client.get(reverse("dat:dat_detail", args=[self.dat.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visibility DAT")
        self.assertContains(response, "Validation actuelle")

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
        self._bind_participant(self.dat, DAT_PORTEUR_ROLE_SLUG, self.other)
        self.client.force_login(self.other)
        response = self.client.get(reverse("dat:my_detail", args=[self.dat.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visibility DAT")
        self.assertContains(response, "Validation actuelle")
        self.assertContains(response, self.other.username)

    def test_admin_can_view_my_detail_page(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("dat:my_detail", args=[self.dat.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visibility DAT")
        self.assertContains(response, "Validation actuelle")

    def _assign_role(self, user, slug):
        role = self.roles[slug]
        user.role = role
        user.save(update_fields=["role"])
        return role

    def _bind_participant(self, dat, slug, user):
        role = self._assign_role(user, slug)
        DATParticipant.objects.update_or_create(
            dat=dat,
            role=role,
            defaults={"user": user},
        )
        return role

    def test_manual_advance_endpoint_is_disabled(self):
        self._bind_participant(self.dat, DAT_PORTEUR_ROLE_SLUG, self.owner)
        self.client.force_login(self.owner)
        response = self.client.post(reverse("dat:my_advance", args=[self.dat.pk]))
        self.assertEqual(response.status_code, 403)
        self.dat.refresh_from_db()
        self.assertEqual(self.dat.status, DATStatus.NOUVELLE_DEMANDE)

    def test_unassigned_user_cannot_advance(self):
        self._assign_role(self.other, DAT_PORTEUR_ROLE_SLUG)
        self.client.force_login(self.other)
        response = self.client.post(reverse("dat:my_advance", args=[self.dat.pk]))
        self.assertEqual(response.status_code, 404)
        self.dat.refresh_from_db()
        self.assertEqual(self.dat.status, DATStatus.NOUVELLE_DEMANDE)

    def test_progress_button_is_hidden(self):
        detail_url = reverse("dat:my_detail", args=[self.dat.pk])

        self.client.force_login(self.owner)
        response = self.client.get(detail_url)
        self.assertNotContains(response, "Passer à l'étape suivante")

        self._bind_participant(self.dat, DAT_PORTEUR_ROLE_SLUG, self.owner)
        response_with_role = self.client.get(detail_url)
        self.assertNotContains(response_with_role, "Passer à l'étape suivante")

    def test_reviewer_can_validate_from_validation_section(self):
        referent = get_user_model().objects.create_user(username="referent-user", password="pwd")
        dat = DAT.objects.create(
            reference="DAT-VIS-REFERENT",
            title="Referent DAT",
            application=self.application,
            status=DATStatus.EN_ATTENTE_DE_REVUE,
            owner=self.owner,
        )
        self._bind_participant(dat, DAT_PORTEUR_ROLE_SLUG, self.owner)
        self._bind_participant(dat, "architecte-referent", referent)

        self.client.force_login(referent)
        response = self.client.post(
            reverse("dat:my_validation_decision", args=[dat.pk]),
            {"decision": "valider"},
        )
        self.assertRedirects(response, reverse("dat:my_detail", args=[dat.pk]))
        dat.refresh_from_db()
        self.assertEqual(dat.status, DATStatus.VALIDER)

    def test_list_only_shows_assigned_dats(self):
        DAT.objects.create(
            reference="DAT-VIS-2",
            title="Other DAT",
            application=self.application,
            status=DATStatus.EN_COURS,
            owner=self.other,
        )
        shared_dat = DAT.objects.create(
            reference="DAT-VIS-3",
            title="Shared DAT",
            application=self.application,
            status=DATStatus.EN_ATTENTE_DE_REVUE,
            owner=self.other,
        )
        self._bind_participant(shared_dat, DAT_PORTEUR_ROLE_SLUG, self.owner)

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

class DatParticipantAssignmentFormTest(TestCase):
    def setUp(self) -> None:
        self.roles: dict[str, Role] = {}
        for slug in DAT_REQUIRED_PARTICIPANT_ROLE_SLUGS:
            label = DAT_REQUIRED_PARTICIPANT_ROLE_LABELS.get(slug, slug)
            self.roles[slug] = create_role(slug, label)
        self.users: dict[str, object] = {}
        User = get_user_model()
        for slug in DAT_REQUIRED_PARTICIPANT_ROLE_SLUGS:
            username = f"{slug.replace('-', '_')}_user"
            user = User.objects.create_user(username=username, password="pwd")
            user.role = self.roles[slug]
            user.save()
            self.users[slug] = user
        self.porteur = self.users[DAT_PORTEUR_ROLE_SLUG]
        direction = get_default_business_direction()
        self.application = Application.objects.create(
            code="form-app",
            name="Form App",
            business_direction=direction,
        )

    def _make_user(self, role_slug: str, suffix: str) -> object:
        User = get_user_model()
        username = f"{role_slug.replace('-', '_')}_{suffix}"
        user = User.objects.create_user(username=username, password="pwd")
        user.role = self.roles[role_slug]
        user.save()
        return user

    def _build_form_data(
        self,
        *,
        reference="DAT-FORM-1",
        title="Form DAT",
        description="Description",
        status=None,
        porteur=None,
        overrides=None,
    ):
        data: dict[str, object] = {
            "reference": reference,
            "title": title,
            "application": self.application.pk,
            "description": description,
            "status": status or DATStatus.NOUVELLE_DEMANDE,
        }
        for slug in DAT_REQUIRED_PARTICIPANT_ROLE_SLUGS:
            user = self.users[slug]
            if slug == DAT_PORTEUR_ROLE_SLUG and porteur is not None:
                user = porteur
            if overrides and slug in overrides:
                user = overrides[slug]
            data[DATForm.participant_field_name(slug)] = user.pk
        return data

    def test_form_creates_required_participants(self):
        form_data = self._build_form_data()
        form = DATForm(data=form_data, user=self.porteur)
        self.assertTrue(form.is_valid(), form.errors)
        dat = form.save()
        dat.refresh_from_db()
        self.assertEqual(dat.owner, self.porteur)
        self.assertEqual(
            dat.participants.filter(role__slug__in=DAT_REQUIRED_PARTICIPANT_ROLE_SLUGS).count(),
            len(DAT_REQUIRED_PARTICIPANT_ROLE_SLUGS),
        )
        for slug in DAT_REQUIRED_PARTICIPANT_ROLE_SLUGS:
            participant = dat.participants.get(role__slug=slug)
            expected_user = self.users[slug]
            self.assertEqual(participant.user, expected_user)

    def test_form_updates_existing_participants(self):
        create_data = self._build_form_data()
        create_form = DATForm(data=create_data, user=self.porteur)
        self.assertTrue(create_form.is_valid(), create_form.errors)
        dat = create_form.save()
        dat.refresh_from_db()

        new_porteur = self._make_user(DAT_PORTEUR_ROLE_SLUG, "alt")
        new_analyste = self._make_user("analyste-secu", "alt")

        update_data = self._build_form_data(
            reference=dat.reference,
            title="Form DAT Updated",
            description="Updated description",
            status=dat.status,
            porteur=new_porteur,
            overrides={"analyste-secu": new_analyste},
        )
        update_form = DATForm(data=update_data, instance=dat, user=self.porteur)
        self.assertTrue(update_form.is_valid(), update_form.errors)
        updated_dat = update_form.save()
        updated_dat.refresh_from_db()

        self.assertEqual(updated_dat.owner, new_porteur)
        self.assertEqual(
            updated_dat.participants.filter(role__slug__in=DAT_REQUIRED_PARTICIPANT_ROLE_SLUGS).count(),
            len(DAT_REQUIRED_PARTICIPANT_ROLE_SLUGS),
        )
        self.assertEqual(
            updated_dat.participants.get(role__slug=DAT_PORTEUR_ROLE_SLUG).user,
            new_porteur,
        )
        self.assertEqual(
            updated_dat.participants.get(role__slug="analyste-secu").user,
            new_analyste,
        )

class ApplicationModelFormattingTest(TestCase):
    def test_formatted_dates(self):
        direction = get_default_business_direction()
        application = Application.objects.create(
            code="format-app",
            name="Format App",
            business_direction=direction,
        )
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
        direction = get_default_business_direction()
        self.application = Application.objects.create(
            code="hist-app",
            name="History App",
            business_direction=direction,
        )
        self.addCleanup(clear_request_context)

    def _create_dat(self) -> DAT:
        dat = DAT(
            reference="DAT-HIST-1",
            title="History Tracking",
            application=self.application,
            status=DATStatus.NOUVELLE_DEMANDE,
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
        self.assertEqual(entry.performed_by, self.user)
        self.assertEqual(entry.actor_name(), self.user.username)

    def test_status_change_records_history_entry(self):
        dat = self._create_dat()
        dat.status = DATStatus.EN_ATTENTE_DE_REVUE
        dat._history_actor = self.manager  # type: ignore[attr-defined]
        dat.save()
        status_entries = dat.history_entries.filter(action=DATHistoryAction.STATUS_CHANGED)
        self.assertEqual(status_entries.count(), 1)
        entry = status_entries.first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.status_change_from, DATStatus.NOUVELLE_DEMANDE.label)
        self.assertEqual(entry.status_change_to, DATStatus.EN_ATTENTE_DE_REVUE.label)
        self.assertEqual(entry.details.get("from"), DATStatus.NOUVELLE_DEMANDE.label)
        self.assertEqual(entry.details.get("to"), DATStatus.EN_ATTENTE_DE_REVUE.label)
        self.assertEqual(entry.performed_by, self.manager)
        self.assertEqual(entry.actor_name(), self.manager.username)
        self.assertEqual(
            dat.history_entries.filter(action=DATHistoryAction.UPDATED).count(),
            0,
        )

    def test_detail_view_displays_history(self):
        dat = self._create_dat()
        dat.status = DATStatus.EN_ATTENTE_DE_REVUE
        dat._history_actor = self.manager  # type: ignore[attr-defined]
        dat.save()
        self.client.force_login(self.manager)
        url = reverse("dat:dat_detail", args=[dat.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Historique du dossier", content)
        self.assertIn(self.manager.username, content)
        self.assertIn(DATStatus.EN_ATTENTE_DE_REVUE.label, content)
        self.assertIn("Passage de", content)

    def test_history_uses_request_context_when_actor_not_set(self):
        bind_request_context(user_id=self.manager.id, username=self.manager.username)
        dat = DAT.objects.create(
            reference="DAT-HIST-CTX",
            title="Request Context Actor",
            application=self.application,
            status=DATStatus.NOUVELLE_DEMANDE,
        )
        entry = dat.history_entries.first()
        self.assertIsNotNone(entry)
        if entry:
            self.assertEqual(entry.action, DATHistoryAction.CREATED)
            self.assertEqual(entry.performed_by_id, self.manager.id)
            self.assertEqual(entry.performed_by_display, self.manager.username)
            self.assertEqual(entry.actor_name(), self.manager.username)


class DatSectionIntegrationTest(TestCase):
    def setUp(self) -> None:
        self.roles = {}
        role_defs = [
            ("porteur-demande", "Porteur de la demande"),
            ("architecte-technique", "Architecte technique"),
            ("architecte-referent", "Architecte referent"),
            ("analyste-secu", "Analyste securite"),
            ("rssi", "RSSI"),
            ("infra-exploitation", "Infra / Exploitation"),
        ]
        for slug, name in role_defs:
            self.roles[slug] = ensure_role(slug, name)

        User = get_user_model()
        self.porteur = User.objects.create_user(username="sections-porteur", password="pwd")
        self.porteur.role = self.roles["porteur-demande"]
        self.porteur.save(update_fields=["role"])
        self.architect = User.objects.create_user(username="sections-architecte", password="pwd")
        self.architect.role = self.roles["architecte-technique"]
        self.architect.save(update_fields=["role"])

        direction = get_default_business_direction()
        self.application = Application.objects.create(
            code="app-sections",
            name="Sections App",
            business_direction=direction,
        )
        self.dat = DAT.objects.create(
            reference="DAT-SECT-1",
            title="DAT Sections",
            application=self.application,
            status=DATStatus.NOUVELLE_DEMANDE,
            owner=self.porteur,
        )
        DATParticipant.objects.create(dat=self.dat, role=self.roles["porteur-demande"], user=self.porteur)

    def test_default_sections_created(self):
        sections = list(self.dat.sections.order_by("order"))
        self.assertEqual(len(sections), 7)
        besoins = next((section for section in sections if section.slug == "besoins"), None)
        self.assertIsNotNone(besoins)
        if besoins:
            self.assertEqual(besoins.sub_sections.count(), 3)
            for part in besoins.sub_sections.all():
                self.assertEqual(part.parts.count(), 0)

    def test_porteur_can_update_section_and_history_logged(self):
        section, sub_section, entry = self._prepare_sub_section_with_entry()
        url = reverse("dat:sub_section_edit", args=[self.dat.pk, section.slug, sub_section.slug])
        self.client.force_login(self.porteur)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        post_data = {
            entry.form_field_name(): "Nouveau besoin prioritaire",
        }
        response = self.client.post(url, post_data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(reverse("dat:my_detail", args=[self.dat.pk])))

        entry.refresh_from_db()
        self.assertEqual(entry.value, "Nouveau besoin prioritaire")

        history_entry = self.dat.history_entries.filter(action=DATHistoryAction.SECTION_UPDATED).first()
        self.assertIsNotNone(history_entry)
        if history_entry and history_entry.details:
            changes = history_entry.details.get("changes", {})
            self.assertIn("besoin_description", changes)

        detail_url = reverse("dat:my_detail", args=[self.dat.pk])
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Description du besoin", content)
        self.assertIn("Nouveau besoin prioritaire", content)

    def _prepare_sub_section_with_entry(self):
        section = self.dat.sections.get(slug="besoins")
        sub_section = section.sub_sections.first()
        if not sub_section:
            self.fail("Section sans sous-section initialisée")
        entry = DATPart.objects.create(
            sub_section=sub_section,
            key="besoin_description",
            label="Description du besoin",
            data_type=DATPartEntryType.LONG_TEXT,
        )
        return section, sub_section, entry

    def test_ajax_get_returns_form_html(self):
        section, sub_section, entry = self._prepare_sub_section_with_entry()
        url = reverse("dat:sub_section_edit", args=[self.dat.pk, section.slug, sub_section.slug])
        self.client.force_login(self.porteur)
        response = self.client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("form_html", payload)
        self.assertIn(entry.label, payload["form_html"])
        self.assertEqual(payload.get("title"), sub_section.title)

    def test_ajax_post_updates_sub_section(self):
        section, sub_section, entry = self._prepare_sub_section_with_entry()
        url = reverse("dat:sub_section_edit", args=[self.dat.pk, section.slug, sub_section.slug])
        self.client.force_login(self.porteur)
        response = self.client.post(
            url,
            {entry.form_field_name(): "Mise à jour via AJAX"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload.get("success"))
        self.assertEqual(payload.get("sub_section_slug"), sub_section.slug)
        self.assertIn(sub_section.slug, payload.get("sub_section_html", ""))
        entry.refresh_from_db()
        self.assertEqual(entry.value, "Mise à jour via AJAX")

    def test_user_without_assignment_cannot_edit_section(self):
        section = self.dat.sections.get(slug="besoins")
        sub_section = section.sub_sections.first()
        url = reverse("dat:sub_section_edit", args=[self.dat.pk, section.slug, sub_section.slug])
        self.client.force_login(self.architect)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_sections_visible_in_detail_view(self):
        self.client.force_login(self.porteur)
        url = reverse("dat:my_detail", args=[self.dat.pk])
        response = self.client.get(url, {"section": "besoins"})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("BESOIN(S)", content)


class CreateSchemaDiagramViewTest(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username="diagram-staff",
            password="pwd",
            is_staff=True,
        )
        direction = get_default_business_direction()
        self.application = Application.objects.create(
            code="app-diagram",
            name="Diagram App",
            business_direction=direction,
        )
        self.dat = DAT.objects.create(
            reference="DAT-DIAG-1",
            title="Schema DAT",
            application=self.application,
            status=DATStatus.NOUVELLE_DEMANDE,
            owner=self.user,
        )
        DATSection.objects.create(
            dat=self.dat,
            title="Architecture",
            slug="architecture",
            order=1,
        )
        self.url = reverse("dat:schema_create_diagram", args=[self.dat.pk])

    def test_rejects_invalid_diagram_title(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.url,
            data=json.dumps({"title": "<script>alert(1)</script>"}),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload.get("ok"))
        self.assertEqual(payload.get("error"), "invalid_title")
        self.assertIn("caract", payload.get("message", "").lower())
        self.assertEqual(Diagram.objects.count(), 0)

    def test_creates_diagram_with_normalized_title(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.url,
            data=json.dumps({"title": "   Nouveau    diagramme   critique   "}),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertTrue(payload.get("ok"))
        diagram_payload = payload.get("diagram") or {}
        self.assertEqual(diagram_payload.get("title"), "Nouveau diagramme critique")
        diagram = Diagram.objects.get(pk=diagram_payload.get("id"))
        self.assertEqual(diagram.owner, self.user)
        self.assertEqual(diagram.title, "Nouveau diagramme critique")

    def test_uses_reference_based_title_when_missing(self):
        self.client.force_login(self.user)
        response = self.client.post(
            self.url,
            data=json.dumps({}),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        diagram_payload = payload.get("diagram") or {}
        self.assertIn("DAT-DIAG-1", diagram_payload.get("title", ""))
        diagram = Diagram.objects.get(pk=diagram_payload.get("id"))
        self.assertTrue(diagram.title.startswith("DAT-DIAG-1"))


class DatPdfExportNotificationTest(TestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(username="pdf-user", password="pwd")
        direction = get_default_business_direction()
        self.application = Application.objects.create(
            code="app-pdf",
            name="Application PDF",
            business_direction=direction,
        )
        self.dat = DAT.objects.create(
            reference="DAT-PDF",
            title="DAT PDF",
            application=self.application,
            status=DATStatus.NOUVELLE_DEMANDE,
            owner=self.user,
        )
        self.client.force_login(self.user)

    @mock.patch("dat.tasks.Thread")
    def test_trigger_pdf_export_sends_user_notification(self, thread_cls):
        thread_instance = mock.Mock()
        thread_cls.return_value = thread_instance
        url = reverse("dat:my_export_pdf_trigger", args=[self.dat.pk])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 302)
        notifications = UserNotification.objects.filter(user=self.user)
        self.assertEqual(notifications.count(), 0)
        thread_instance.start.assert_called_once()

    @mock.patch("dat.tasks.store_dat_pdf_export")
    @mock.patch("dat.tasks.generate_dat_pdf")
    def test_pdf_generation_completion_creates_notification(self, generate_pdf, store_pdf):
        generate_pdf.return_value = (b"%PDF", {})
        store_pdf.return_value = "dat/path.pdf"
        DAT.objects.filter(pk=self.dat.pk).update(
            pdf_export_in_progress=True,
            pdf_export_requested_by=self.user,
            pdf_export_requested_by_display="PDF User",
        )

        _run_pdf_generation(self.dat.pk, base_url=None)

        notification = UserNotification.objects.get(user=self.user)
        self.assertEqual(notification.title, "Export PDF disponible")
        self.assertEqual(notification.dat, self.dat)
        self.assertEqual(notification.level, "success")
        self.assertIn("prêt", notification.message)


class DatReserveNotificationTest(TestCase):
    def setUp(self) -> None:
        self.admin = get_user_model().objects.create_user(
            username="reserve-admin",
            password="pwd",
            is_staff=True,
        )
        self.manager = get_user_model().objects.create_user(
            username="reserve-manager",
            password="pwd",
        )
        self.assignee = get_user_model().objects.create_user(
            username="reserve-assignee",
            password="pwd",
        )
        self.role_architecture = ensure_role("architecte-technique", "Architecte technique")
        self.assignee.role = self.role_architecture
        self.assignee.save(update_fields=["role"])
        self.group = BusinessGroup.objects.create(
            name="Groupe reserve",
            direction=get_default_technical_direction(),
            responsible=self.manager,
        )
        self.assignee.business_group = self.group
        self.assignee.save(update_fields=["business_group"])
        self.application = Application.objects.create(
            code="app-reserve",
            name="Application Reserve",
            business_direction=get_default_business_direction(),
        )
        self.dat = DAT.objects.create(
            reference="DAT-RESERVE",
            title="DAT Reserve",
            application=self.application,
            status=DATStatus.EN_COURS,
            owner=self.assignee,
        )
        sync_dat_sections_if_needed(self.dat)
        DATParticipant.objects.create(dat=self.dat, role=self.role_architecture, user=self.assignee)
        self.section_slug = "architecture"
        self.reserve_url = reverse("dat:section_reserve", args=[self.dat.pk, self.section_slug])
        self.status_url = reverse("dat:section_status", args=[self.dat.pk, self.section_slug])

    def _set_reserve(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            self.reserve_url,
            data={"reserve_message": "Corriger la section."},
        )
        self.assertEqual(response.status_code, 302)

    def test_reserve_notifies_participant_and_manager(self):
        self._set_reserve()
        self.assertTrue(
            UserNotification.objects.filter(
                user=self.assignee,
                notification_type__title="Réserve sur votre section",
            ).exists()
        )
        self.assertTrue(
            UserNotification.objects.filter(
                user=self.manager,
                notification_type__title="Réserve sur votre section",
            ).exists()
        )

    def test_validation_notifies_reserve_author(self):
        self._set_reserve()
        self.client.force_login(self.assignee)
        response = self.client.post(
            self.status_url,
            data={"status": SECTION_STATUS_VALIDATED_VALUE},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            UserNotification.objects.filter(
                user=self.admin,
                notification_type__title="Réserve à lever",
            ).exists()
        )


class SectionStatusGroupResponsibleTest(TestCase):
    def setUp(self) -> None:
        User = get_user_model()
        self.manager = User.objects.create_user(username="group-manager", password="pwd")
        self.technical_direction = get_default_technical_direction()
        self.role_architecture = ensure_role("architecte-technique", "Architecte technique")
        self.group = BusinessGroup.objects.create(
            name="Groupe technique test",
            direction=self.technical_direction,
            responsible=self.manager,
        )
        self.member = User.objects.create_user(
            username="archi-user",
            password="pwd",
            role=self.role_architecture,
            business_group=self.group,
        )
        self.application = Application.objects.create(
            code="app-group",
            name="Application Groupe",
            business_direction=get_default_business_direction(),
        )
        self.dat = DAT.objects.create(
            reference="DAT-GROUP-001",
            title="DAT group validation",
            application=self.application,
            status=DATStatus.EN_COURS,
            owner=self.member,
        )
        DATParticipant.objects.create(dat=self.dat, role=self.role_architecture, user=self.member)
        sync_dat_sections_if_needed(self.dat)

    def test_group_responsible_can_view_dat_and_validate_architecture(self):
        self.client.force_login(self.manager)
        detail_url = reverse("dat:my_detail", args=[self.dat.pk]) + "?section=validation"
        response = self.client.get(detail_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            reverse("dat:section_status", args=[self.dat.pk, "architecture"]),
            response.content.decode(),
        )
        response = self.client.post(
            reverse("dat:section_status", args=[self.dat.pk, "architecture"]),
            {"status": "valide"},
        )
        self.assertEqual(response.status_code, 302)
        from .views import build_section_status_map

        status_map, _choices = build_section_status_map(DAT.objects.get(pk=self.dat.pk))
        self.assertEqual(status_map["architecture"]["value"], "valide")

    def test_group_responsible_cannot_validate_unassigned_section(self):
        self.client.force_login(self.manager)
        response = self.client.post(
            reverse("dat:section_status", args=[self.dat.pk, "urbanisme"]),
            {"status": "valide"},
        )
        self.assertEqual(response.status_code, 403)
