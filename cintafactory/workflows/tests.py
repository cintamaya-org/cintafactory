from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from dat.models import Application, DAT, DATParticipant, DATStatus, DATHistory, DATHistoryAction
from users.models import BusinessDirection, Role, TechnicalDirection
from .models import NotificationMessage, NotificationType, Workflow, UserNotification
from .notifications import SESSION_SEEN_KEY
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
        self.roles = {slug: create_role(slug, name) for slug, name in ROLE_FIXTURES.items()}

    def test_sync_creates_workflow_steps_and_permissions(self):
        sync_workflow_definitions()

        workflow = Workflow.objects.get(code="dat-validation")
        steps = list(workflow.steps.order_by("order"))

        self.assertEqual(len(steps), 6)
        draft = next(step for step in steps if step.key == "nouvelle-demande")
        self.assertTrue(draft.is_initial)
        self.assertEqual(draft.write_permissions.count(), 1)
        self.assertEqual(draft.write_permissions.first().role, self.roles["porteur-demande"])

        review_step = next(step for step in steps if step.key == "en-attente-revue")
        self.assertEqual(
            {perm.role for perm in review_step.write_permissions},
            {
                self.roles["architecte-referent"],
                self.roles["comite-validation"],
            },
        )
        review_read_roles = {perm.role for perm in review_step.read_permissions}
        self.assertIn(self.roles["porteur-demande"], review_read_roles)


class WorkflowBoardViewTests(TestCase):
    def setUp(self):
        self.roles = {slug: create_role(slug, name) for slug, name in ROLE_FIXTURES.items()}
        sync_workflow_definitions()
        self.user = get_user_model().objects.create_user(username="architect", password="pwd")
        self.other_user = get_user_model().objects.create_user(username="other-user", password="pwd")
        self.client = Client()
        self.client.force_login(self.user)
        self.business_direction = get_default_business_direction()
        self.application = Application.objects.create(
            code="workflow-app",
            name="Workflow App",
            business_direction=self.business_direction,
        )

    def test_board_renders_columns_with_dat_items(self):
        DAT.objects.create(
            reference="DAT-001",
            title="Initial",
            status=DATStatus.NOUVELLE_DEMANDE,
            application=self.application,
            owner=self.user,
        )
        DAT.objects.create(
            reference="DAT-002",
            title="Technique",
            status=DATStatus.EN_COURS,
            application=self.application,
            owner=self.user,
        )
        DAT.objects.create(
            reference="DAT-003",
            title="Referent",
            status=DATStatus.EN_ATTENTE_DE_REVUE,
            application=self.application,
            owner=self.user,
        )

        response = self.client.get(reverse("workflows:index"))

        self.assertEqual(response.status_code, 200)
        columns = response.context["columns"]
        self.assertEqual(len(columns), 3)

        initial_column = columns[0]
        self.assertEqual(initial_column["status_codes"], [DATStatus.NOUVELLE_DEMANDE])
        self.assertEqual(len(initial_column["items"]), 1)
        self.assertContains(response, "DAT-001")
        self.assertContains(response, "En cours")

        in_progress_column = columns[1]
        in_progress_statuses = set(in_progress_column["status_codes"])
        self.assertIn(DATStatus.EN_COURS, in_progress_statuses)
        self.assertIn(DATStatus.EN_ATTENTE_DE_REVUE, columns[1]["status_codes"])

    def test_board_alias_works(self):
        response = self.client.get(reverse("workflows:board"))
        self.assertEqual(response.status_code, 200)

    def test_board_hides_unassigned_dats(self):
        DAT.objects.create(
            reference="DAT-OWNED",
            title="My DAT",
            status=DATStatus.NOUVELLE_DEMANDE,
            application=self.application,
            owner=self.user,
        )
        DAT.objects.create(
            reference="DAT-FOREIGN",
            title="Other DAT",
            status=DATStatus.EN_COURS,
            application=self.application,
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
            status=DATStatus.NOUVELLE_DEMANDE,
            application=self.application,
        )
        DAT.objects.create(
            reference="DAT-ADMIN-2",
            title="Admin Visible 2",
            status=DATStatus.EN_ATTENTE_DE_REVUE,
            application=self.application,
            owner=self.other_user,
        )

        self.client.force_login(admin)
        response = self.client.get(reverse("workflows:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "DAT-ADMIN-1")
        self.assertContains(response, "DAT-ADMIN-2")

    def test_progress_button_not_rendered(self):
        referent_role = self.roles["architecte-referent"]
        porteur_role = self.roles["porteur-demande"]
        porteur = get_user_model().objects.create_user(username="board-porteur", password="pwd")
        dat = DAT.objects.create(
            reference="DAT-BOARD-REF",
            title="Board Referent",
            status=DATStatus.EN_ATTENTE_DE_REVUE,
            application=self.application,
            owner=porteur,
        )
        DATParticipant.objects.create(dat=dat, role=porteur_role, user=porteur)
        self.user.role = referent_role
        self.user.save(update_fields=["role"])
        DATParticipant.objects.create(dat=dat, role=referent_role, user=self.user)

        response = self.client.get(reverse("workflows:index"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Passer a l'etape suivante")


class WorkflowNotificationsViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="notif-user", password="pwd")
        self.client = Client()
        self.client.force_login(self.user)
        direction = get_default_business_direction()
        self.application = Application.objects.create(
            code="app-notif",
            name="Application Notifications",
            business_direction=direction,
        )
        self.dat = DAT.objects.create(
            reference="DAT-NOTIF",
            title="DAT Notifications",
            application=self.application,
            status=DATStatus.NOUVELLE_DEMANDE,
            owner=self.user,
        )
        self.history = DATHistory.objects.create(
            dat=self.dat,
            action=DATHistoryAction.STATUS_CHANGED,
            status_before=DATStatus.NOUVELLE_DEMANDE,
            status_after=DATStatus.EN_ATTENTE_DE_REVUE,
            performed_by=self.user,
            performed_by_display="Notif User",
            details={"from": "Nouvelle demande", "to": "En Attente de revue"},
        )
        self.notification_type = NotificationType.objects.create(
            title="Export PDF lancé",
            level=NotificationType.LEVEL_INFO,
        )
        self.notification_message = NotificationMessage.objects.create(
            content="Votre export PDF est en préparation.",
        )
        self.user_notification = UserNotification.objects.create(
            user=self.user,
            notification_type=self.notification_type,
            notification_message=self.notification_message,
            dat=self.dat,
            target_url="/dat/1/",
        )

    def test_notifications_view_combines_sources_and_marks_as_viewed(self):
        response = self.client.get(reverse("workflows:notifications"))
        self.assertEqual(response.status_code, 200)
        notifications = response.context["notifications"]
        self.assertEqual(len(notifications), 2)
        self.assertContains(response, "Export PDF lancé")
        self.assertContains(response, "En Attente de revue")

        session = self.client.session
        seen_ids = session.get(SESSION_SEEN_KEY, [])
        self.assertIn(self.history.id, seen_ids)

        self.user_notification.refresh_from_db()
        self.assertIsNotNone(self.user_notification.viewed_at)
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
