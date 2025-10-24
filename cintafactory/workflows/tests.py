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
    "architecte-referent": "Architecte Référent",
    "architecte-technique": "Architecte Technique",
    "urbaniste": "Urbaniste",
    "analyste-secu": "Analyste Sécu",
    "rssi": "RSSI",
    "comite-validation": "Comité de validation",
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

        self.assertEqual(len(steps), 17)
        draft = next(step for step in steps if step.key == "besoin-dal")
        self.assertTrue(draft.is_initial)
        self.assertEqual(draft.write_permissions.count(), 1)
        self.assertEqual(draft.write_permissions.first().role, self.roles["porteur-demande"])

        security = next(step for step in steps if step.key == "preconisation-securite")
        self.assertGreaterEqual(security.read_permissions.count(), 2)
        self.assertSetEqual(
            {perm.role for perm in security.read_permissions},
            {
                self.roles["architecte-technique"],
                self.roles["analyste-secu"],
                self.roles["rssi"],
            },
        )


class WorkflowBoardViewTests(TestCase):
    def setUp(self):
        self.roles = {
            slug: Role.objects.create(name=name, slug=slug)
            for slug, name in ROLE_FIXTURES.items()
        }
        sync_workflow_definitions()
        self.user = get_user_model().objects.create_user(username="architect", password="pwd")
        self.client = Client()
        self.client.force_login(self.user)

    def test_board_renders_columns_with_dat_items(self):
        DAT.objects.create(reference="DAT-001", title="Initial", status=DATStatus.BESOIN_DAL)
        DAT.objects.create(reference="DAT-002", title="Dossier", status=DATStatus.NOUVEAU_DOSSIER)
        DAT.objects.create(reference="DAT-003", title="Referent", status=DATStatus.VALIDATION_REFERENT)

        response = self.client.get(reverse("workflows:index"))

        self.assertEqual(response.status_code, 200)
        columns = response.context["columns"]
        self.assertEqual(len(columns), 17)
        draft_column = columns[0]
        self.assertEqual(draft_column["step"].key, "besoin-dal")
        self.assertEqual(draft_column["items"].count(), 1)
        self.assertContains(response, "DAT-001")
        self.assertContains(response, "Validation du référent")

    def test_board_alias_works(self):
        response = self.client.get(reverse("workflows:board"))
        self.assertEqual(response.status_code, 200)
