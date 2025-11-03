from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from dat.models import DAT, DATStatus
from users.models import Role
from .models import Workflow
from .sync import sync_workflow_definitions


ROLE_FIXTURES = {
    "porteur-demande": "Porteur de la demande",
    "architecte-referent": "Architecte Referent",
    "architecte-technique": "Architecte Technique",
    "urbaniste": "Urbaniste",
    "analyste-secu": "Analyste Secu",
    "rssi": "RSSI",
    "infra-exploitation": "Infra / Exploitation",
    "comite-validation": "Comite de validation",
}


class WorkflowSyncTests(TestCase):
    def setUp(self):
        self.roles = {
            slug: Role.objects.create(name=name, slug=slug)
            for slug, name in ROLE_FIXTURES.items()
        }

    def test_sync_creates_workflow_steps_and_permissions(self):
        sync_workflow_definitions()

        workflow = Workflow.objects.get(code="dat-validation")
        steps = list(workflow.steps.order_by("order"))

        self.assertEqual(len(steps), 11)
        draft = next(step for step in steps if step.key == "demande-initiale")
        self.assertTrue(draft.is_initial)
        self.assertEqual(draft.write_permissions.count(), 1)
        self.assertEqual(draft.write_permissions.first().role, self.roles["porteur-demande"])

        security = next(step for step in steps if step.key == "analyse-securite")
        self.assertEqual(
            {perm.role for perm in security.write_permissions},
            {self.roles["analyste-secu"]},
        )
        security_read_roles = {perm.role for perm in security.read_permissions}
        self.assertIn(self.roles["architecte-technique"], security_read_roles)
        self.assertIn(self.roles["rssi"], security_read_roles)


class WorkflowBoardViewTests(TestCase):
    def setUp(self):
        self.roles = {
            slug: Role.objects.create(name=name, slug=slug)
            for slug, name in ROLE_FIXTURES.items()
        }
        sync_workflow_definitions()
        self.user = get_user_model().objects.create_user(username="architect", password="pwd")
        self.other_user = get_user_model().objects.create_user(username="other-user", password="pwd")
        self.client = Client()
        self.client.force_login(self.user)

    def test_board_renders_columns_with_dat_items(self):
        DAT.objects.create(
            reference="DAT-001",
            title="Initial",
            status=DATStatus.DEMANDE_INITIALE,
            owner=self.user,
        )
        DAT.objects.create(
            reference="DAT-002",
            title="Technique",
            status=DATStatus.INSTRUCTION_ARCHITECTURE,
            owner=self.user,
        )
        DAT.objects.create(
            reference="DAT-003",
            title="Referent",
            status=DATStatus.VALIDATION_REFERENT,
            owner=self.user,
        )

        response = self.client.get(reverse("workflows:index"))

        self.assertEqual(response.status_code, 200)
        columns = response.context["columns"]
        self.assertEqual(len(columns), 3)

        initial_column = columns[0]
        self.assertEqual(initial_column["status_codes"], [DATStatus.DEMANDE_INITIALE])
        self.assertEqual(len(initial_column["items"]), 1)
        self.assertContains(response, "DAT-001")
        self.assertContains(response, "Validation du referent")

        in_progress_column = columns[1]
        in_progress_statuses = set(in_progress_column["status_codes"])
        self.assertIn(DATStatus.INSTRUCTION_ARCHITECTURE, in_progress_statuses)
        self.assertIn(DATStatus.VALIDATION_REFERENT, columns[1]["status_codes"])

    def test_board_alias_works(self):
        response = self.client.get(reverse("workflows:board"))
        self.assertEqual(response.status_code, 200)

    def test_board_hides_unassigned_dats(self):
        DAT.objects.create(
            reference="DAT-OWNED",
            title="My DAT",
            status=DATStatus.DEMANDE_INITIALE,
            owner=self.user,
        )
        DAT.objects.create(
            reference="DAT-FOREIGN",
            title="Other DAT",
            status=DATStatus.INSTRUCTION_ARCHITECTURE,
            owner=self.other_user,
        )

        response = self.client.get(reverse("workflows:index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "DAT-OWNED")
        self.assertNotContains(response, "DAT-FOREIGN")

    def test_board_admin_sees_all_dats(self):
        admin = get_user_model().objects.create_user(
            username="board-admin",
            password="pwd",
            is_staff=True,
        )
        DAT.objects.create(
            reference="DAT-ADMIN-1",
            title="Admin Visible",
            status=DATStatus.DEMANDE_INITIALE,
        )
        DAT.objects.create(
            reference="DAT-ADMIN-2",
            title="Admin Visible 2",
            status=DATStatus.VALIDATION_REFERENT,
            owner=self.other_user,
        )

        self.client.force_login(admin)
        response = self.client.get(reverse("workflows:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "DAT-ADMIN-1")
        self.assertContains(response, "DAT-ADMIN-2")
