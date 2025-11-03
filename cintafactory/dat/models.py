from django.conf import settings
from django.db import models
from django.utils import timezone


class DATStatus(models.TextChoices):
    DEMANDE_INITIALE = "demande_initiale", "Demande initiale"
    VALIDATION_REFERENT = "validation_referent", "Validation du referent"
    INSTRUCTION_ARCHITECTURE = "instruction_architecture", "Instruction architecture technique"
    INSTRUCTION_URBANISME = "instruction_urbanisme", "Instruction urbanisme"
    ANALYSE_SECURITE = "analyse_securite", "Analyse cyber securite"
    GENERATION_CARTOGRAPHIE = "generation_cartographie", "Generation cartographie et inventaire"
    REVUE_INFRA_EXPLOITATION = "revue_infra_exploitation", "Revue infra / exploitation"
    VALIDATION_FINALE = "validation_finale", "Validation finale pluridisciplinaire"
    VALIDATION_RESERVE = "validation_reserve", "Validation avec reserve"
    DAT_REFUSE = "dat_refuse", "DAT refuse"
    DAT_VALIDE = "dat_valide", "DAT valide"


class Application(models.Model):
    code = models.SlugField(max_length=64, unique=True, verbose_name="Code")
    name = models.CharField(max_length=200, verbose_name="Nom")
    description = models.TextField(blank=True, verbose_name="Description")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Mis à jour le")

    class Meta:
        db_table = "dat_application"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def formatted_created_at(self) -> str:
        if not self.created_at:
            return ""
        reference = timezone.localtime(self.created_at)
        return reference.strftime("%d/%m/%Y à %Hh%M")

    formatted_created_at.short_description = "Créé le"
    formatted_created_at.admin_order_field = "created_at"

    def formatted_updated_at(self) -> str:
        if not self.updated_at:
            return ""
        reference = timezone.localtime(self.updated_at)
        return reference.strftime("%d/%m/%Y à %Hh%M")

    formatted_updated_at.short_description = "Mis à jour le"
    formatted_updated_at.admin_order_field = "updated_at"


class DAT(models.Model):

    reference = models.CharField(max_length=64, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    application = models.ForeignKey(
        Application,
        on_delete=models.PROTECT,
        related_name="dats",
    )
    status = models.CharField(
        max_length=64,
        choices=DATStatus.choices,
        default=DATStatus.DEMANDE_INITIALE,
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dats",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "dat_dat"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reference} - {self.title}"


class DATParticipant(models.Model):
    dat = models.ForeignKey(
        DAT,
        on_delete=models.CASCADE,
        related_name="participants",
        verbose_name="DAT",
    )
    role = models.ForeignKey(
        "users.Role",
        on_delete=models.PROTECT,
        related_name="dat_participants",
        verbose_name="Rôle",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="dat_participations",
        verbose_name="Utilisateur",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dat_participant"
        constraints = [
            models.UniqueConstraint(
                fields=["dat", "role"],
                name="dat_participant_unique_role_per_dat",
            ),
            models.UniqueConstraint(
                fields=["dat", "user"],
                name="dat_participant_unique_user_per_dat",
            ),
        ]
        ordering = ["dat_id", "role__name", "user__username"]
        verbose_name = "Participant du DAT"
        verbose_name_plural = "Participants du DAT"

    def __str__(self) -> str:
        return f"{self.dat.reference} - {self.role.name} - {self.user.get_username()}"


class DATHistoryAction(models.TextChoices):
    CREATED = "created", "Création"
    UPDATED = "updated", "Mise à jour"
    STATUS_CHANGED = "status_changed", "Changement de statut"
    OWNER_CHANGED = "owner_changed", "Changement de responsable"
    DELETED = "deleted", "Suppression"


class DATHistory(models.Model):
    dat = models.ForeignKey(
        DAT,
        on_delete=models.CASCADE,
        related_name="history_entries",
    )
    action = models.CharField(
        max_length=32,
        choices=DATHistoryAction.choices,
    )
    status_before = models.CharField(
        max_length=64,
        choices=DATStatus.choices,
        blank=True,
        null=True,
    )
    status_after = models.CharField(
        max_length=64,
        choices=DATStatus.choices,
        blank=True,
        null=True,
    )
    performed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="dat_history_entries",
    )
    performed_by_display = models.CharField(max_length=255, blank=True)
    details = models.JSONField(blank=True, null=True)
    performed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dat_history"
        ordering = ["-performed_at", "-id"]

    def actor_name(self) -> str:
        if self.performed_by_display:
            return self.performed_by_display
        if self.performed_by:
            full_name = self.performed_by.get_full_name()
            if full_name:
                return full_name
            return self.performed_by.get_username()
        return "Système"

    def formatted_performed_at(self) -> str:
        reference = timezone.localtime(self.performed_at)
        return reference.strftime("%d/%m/%Y à %Hh%M")

    def __str__(self) -> str:
        username = self.actor_name()
        timestamp = timezone.localtime(self.performed_at)
        return f"{self.get_action_display()} par {username} le {timestamp.strftime('%d/%m/%Y %H:%M:%S')}"
