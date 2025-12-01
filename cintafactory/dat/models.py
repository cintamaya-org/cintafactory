import hashlib
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

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
    business_direction = models.ForeignKey(
        "users.BusinessDirection",
        on_delete=models.PROTECT,
        related_name="applications",
        verbose_name="Direction métier",
    )
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
    business_direction = models.ForeignKey(
        "users.BusinessDirection",
        on_delete=models.PROTECT,
        related_name="dats",
        verbose_name="Direction métier",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    pdf_export_in_progress = models.BooleanField(default=False)
    pdf_export_requested_at = models.DateTimeField(blank=True, null=True)
    pdf_export_requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    pdf_export_requested_by_display = models.CharField(max_length=255, blank=True)

    class Meta:
        db_table = "dat_dat"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.reference} - {self.title}"

    def sync_business_direction(self):
        if not self.application_id:
            self.business_direction_id = None
            return
        application = getattr(self, "application", None)
        if application is None or application.pk != self.application_id:
            application = Application.objects.filter(pk=self.application_id).only("business_direction_id").first()
        if application:
            self.business_direction_id = application.business_direction_id

    def save(self, *args, **kwargs):
        self.sync_business_direction()
        super().save(*args, **kwargs)


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
    SECTION_UPDATED = "section_updated", "Section mise à jour"
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


class DATSection(models.Model):
    dat = models.ForeignKey(
        DAT,
        on_delete=models.CASCADE,
        related_name="sections",
        verbose_name="DAT",
    )
    title = models.CharField(max_length=200, verbose_name="Titre")
    slug = models.SlugField(max_length=100, verbose_name="Identifiant")
    order = models.PositiveIntegerField(default=0, verbose_name="Ordre")
    description = models.TextField(blank=True, verbose_name="Description")
    allowed_roles = models.ManyToManyField(
        "users.Role",
        related_name="editable_dat_sections",
        blank=True,
        verbose_name="Rôles autorisés",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Mis à jour le")

    class Meta:
        db_table = "dat_section"
        ordering = ["order", "id"]
        unique_together = (("dat", "slug"),)
        verbose_name = "Section de DAT"
        verbose_name_plural = "Sections de DAT"

    def __str__(self) -> str:
        return f"{self.dat.reference} - {self.title}"

    def can_user_edit(self, user) -> bool:
        if user is None or not getattr(user, "is_authenticated", False):
            return False
        from .permissions import user_is_dat_admin

        if user_is_dat_admin(user):
            return True
        role = getattr(user, "role", None)
        if role is None:
            return False
        allowed_role_ids = getattr(self, "_allowed_role_ids_cache", None)
        if allowed_role_ids is None:
            allowed_role_ids = set(self.allowed_roles.values_list("pk", flat=True))
            self._allowed_role_ids_cache = allowed_role_ids
        if role.pk not in allowed_role_ids:
            return False
        participants = getattr(self.dat, "_participants_cache", None)
        if participants is None:
            participants = list(self.dat.participants.all())
            self.dat._participants_cache = participants  # type: ignore[attr-defined]
        user_id = getattr(user, "id", None)
        for participant in participants:
            if participant.user_id == user_id and participant.role_id == role.pk:
                return True
        return False


class DATSubSection(models.Model):
    section = models.ForeignKey(
        DATSection,
        on_delete=models.CASCADE,
        related_name="sub_sections",
        verbose_name="Section",
    )
    title = models.CharField(max_length=200, verbose_name="Titre")
    slug = models.SlugField(max_length=100, verbose_name="Identifiant")
    order = models.PositiveIntegerField(default=0, verbose_name="Ordre")
    description = models.TextField(blank=True, verbose_name="Description")
    allowed_roles = models.ManyToManyField(
        "users.Role",
        related_name="editable_dat_sub_sections",
        blank=True,
        verbose_name="Rôles autorisés",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Mis à jour le")

    class Meta:
        db_table = "dat_sub_section"
        ordering = ["order", "id"]
        unique_together = (("section", "slug"),)
        verbose_name = "Sous-section de DAT"
        verbose_name_plural = "Sous-sections de DAT"

    def __str__(self) -> str:
        return f"{self.section.dat.reference} - {self.section.title} - {self.title}"

    def can_user_edit(self, user) -> bool:
        if getattr(self, "section", None) and getattr(self.section, "slug", None) == "validation":
            return False
        if self.section is None:
            return False
        if not getattr(user, "is_authenticated", False):
            return False
        from .permissions import user_is_dat_admin

        if user_is_dat_admin(user):
            return True
        allowed_roles_qs = self.allowed_roles.all()
        if not allowed_roles_qs.exists():
            return self.section.can_user_edit(user)
        role = getattr(user, "role", None)
        if role is None:
            return False
        allowed_role_ids = getattr(self, "_allowed_role_ids_cache", None)
        if allowed_role_ids is None:
            allowed_role_ids = set(allowed_roles_qs.values_list("pk", flat=True))
            self._allowed_role_ids_cache = allowed_role_ids
        if role.pk not in allowed_role_ids:
            return False
        dat = self.section.dat
        participants = getattr(dat, "_participants_cache", None)
        if participants is None:
            participants = list(dat.participants.all())
            dat._participants_cache = participants  # type: ignore[attr-defined]
        user_id = getattr(user, "id", None)
        for participant in participants:
            if participant.user_id == user_id and participant.role_id == role.pk:
                return True
        return False


class DATPartEntryType(models.TextChoices):
    TEXT = "text", "Texte"
    LONG_TEXT = "long_text", "Texte long"
    INTEGER = "integer", "Nombre entier"
    DECIMAL = "decimal", "Nombre décimal"
    DATE = "date", "Date"
    BOOLEAN = "boolean", "Booléen"
    JSON = "json", "JSON"
    URL = "url", "Lien"
    REPEATER = "repeater", "Tableau dynamique"


class DATPart(models.Model):
    sub_section = models.ForeignKey(
        DATSubSection,
        on_delete=models.CASCADE,
        related_name="parts",
        verbose_name="Sous-section",
    )
    key = models.SlugField(max_length=100, verbose_name="Clé")
    label = models.CharField(max_length=200, verbose_name="Libellé")
    data_type = models.CharField(
        max_length=20,
        choices=DATPartEntryType.choices,
        default=DATPartEntryType.TEXT,
        verbose_name="Type de donnée",
    )
    required = models.BooleanField(default=False, verbose_name="Obligatoire")
    order = models.PositiveIntegerField(default=0, verbose_name="Ordre")
    config = models.JSONField(blank=True, null=True, verbose_name="Configuration")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Mis à jour le")

    class Meta:
        db_table = "dat_part"
        ordering = ["order", "id"]
        unique_together = (("sub_section", "key"),)
        verbose_name = "Partie de DAT"
        verbose_name_plural = "Parties de DAT"

    def __str__(self) -> str:
        return (
            f"{self.sub_section.section.dat.reference} - {self.sub_section.section.title} - "
            f"{self.sub_section.title} - {self.label}"
        )

    def _get_current_entry(self):
        entry = getattr(self, "_current_entry_cache", None)
        if entry is not None:
            return entry
        prefetched = getattr(self, "_prefetched_objects_cache", None)
        if prefetched and "entries" in prefetched:
            entries = prefetched["entries"] or []
            entries = sorted(
                entries,
                key=lambda item: (
                    item.updated_at or datetime.min.replace(tzinfo=timezone.utc),
                    item.pk or 0,
                ),
                reverse=True,
            )
            entry = entries[0] if entries else None
        else:
            entry = self.entries.order_by("-updated_at", "-id").first()
        self._current_entry_cache = entry
        return entry

    def _set_entry_cache(self, entry):
        self._current_entry_cache = entry

    @property
    def value(self):
        entry = self._get_current_entry()
        if entry is None:
            return None
        return entry.resolved_value

    @value.setter
    def value(self, new_value):
        self.update_value(new_value)

    def form_field_name(self) -> str:
        return f"entry_{self.pk or self.key}"

    def initial_value(self):
        value = self.value
        if value in (None, ""):
            return None
        if self.data_type == DATPartEntryType.BOOLEAN:
            return bool(value)
        if self.data_type == DATPartEntryType.INTEGER:
            try:
                return int(value)
            except (TypeError, ValueError):
                return value
        if self.data_type == DATPartEntryType.DECIMAL:
            try:
                return Decimal(str(value))
            except (TypeError, InvalidOperation):
                return value
        if self.data_type == DATPartEntryType.DATE:
            if isinstance(value, date):
                return value
            if isinstance(value, str):
                try:
                    return date.fromisoformat(value)
                except ValueError:
                    return value
        return value

    def prepare_value(self, value):
        if value in (None, ""):
            return None
        config = self.config or {}
        if config.get("multiple") and isinstance(value, (list, tuple)):
            return list(value)
        if self.data_type == DATPartEntryType.BOOLEAN:
            return bool(value)
        if self.data_type == DATPartEntryType.INTEGER:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
        if self.data_type == DATPartEntryType.DECIMAL:
            if isinstance(value, Decimal):
                return str(value)
            try:
                return str(Decimal(str(value)))
            except (TypeError, InvalidOperation):
                return None
        if self.data_type == DATPartEntryType.DATE:
            if isinstance(value, date):
                return value.isoformat()
            return str(value)
        if self.data_type == DATPartEntryType.REPEATER:
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                except json.JSONDecodeError:
                    return []
            else:
                parsed = value
            if isinstance(parsed, list):
                return parsed
            return []
        return value

    def update_value(self, prepared):
        payload = DATPartPayload.get_or_create_for_value(prepared)
        entry = self._get_current_entry()
        if entry is None:
            entry = DATPartEntry.objects.create(
                part=self,
                payload=payload,
            )
        else:
            entry.payload = payload
            entry.save(update_fields=["payload", "updated_at"])
        self._set_entry_cache(entry)
        return entry

    def render_value(self, value):
        if value in (None, "", []):
            return ""
        config = self.config or {}
        choices = config.get("choices") if isinstance(config, dict) else None
        if choices:
            choice_map = {item.get("value"): item.get("label", item.get("value")) for item in choices}
            if config.get("multiple") and isinstance(value, (list, tuple)):
                return ", ".join(str(choice_map.get(item, item)) for item in value)
            return str(choice_map.get(value, value))
        if self.data_type == DATPartEntryType.BOOLEAN:
            return "Oui" if bool(value) else "Non"
        if self.data_type == DATPartEntryType.DATE:
            if hasattr(value, "isoformat"):
                return value.isoformat()
            return str(value)
        if self.data_type == DATPartEntryType.INTEGER:
            return str(value)
        if self.data_type == DATPartEntryType.DECIMAL:
            return str(value)
        if self.data_type == DATPartEntryType.JSON:
            if isinstance(value, (dict, list)):
                return json.dumps(value, ensure_ascii=False, indent=2)
            return str(value)
        if self.data_type == DATPartEntryType.REPEATER:
            if isinstance(value, list):
                return value
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                except json.JSONDecodeError:
                    return []
                if isinstance(parsed, list):
                    return parsed
            return []
        return str(value)

    def formatted_value(self) -> str:
        return self.render_value(self.value)


class DATPartEntry(models.Model):
    payload = models.ForeignKey(
        "DATPartPayload",
        on_delete=models.PROTECT,
        related_name="entries",
        null=True,
        blank=True,
        verbose_name="Payload dédupliqué",
    )
    part = models.ForeignKey(
        DATPart,
        on_delete=models.CASCADE,
        related_name="entries",
        verbose_name="Partie",
        db_index=False,
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Mis à jour le")

    class Meta:
        db_table = "dat_part_entry"
        ordering = ["-updated_at", "-id"]
        verbose_name = "Valeur de partie de DAT"
        verbose_name_plural = "Valeurs de parties de DAT"
        indexes = [
            models.Index(fields=["part"], name="dat_part_entry_part_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.part}"

    @property
    def resolved_value(self):
        if self.payload_id:
            return getattr(self.payload, "data", None)
        return None

    @property
    def value(self):  # backwards compatibility
        return self.resolved_value

    @value.setter
    def value(self, new_value):
        payload = DATPartPayload.get_or_create_for_value(new_value)
        self.payload = payload


class DATPartPayload(models.Model):
    hash = models.CharField(max_length=64, unique=True, db_index=True)
    data = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dat_part_payload"
        ordering = ["hash"]

    def __str__(self) -> str:
        return self.hash

    def save(self, *args, **kwargs):
        # Payloads are immutable once created to avoid breaking entries that share them.
        if self.pk:
            existing = type(self).objects.filter(pk=self.pk).values_list("data", flat=True).first()
            if existing is not None:
                self.data = existing
        super().save(*args, **kwargs)

    @staticmethod
    def _normalize_for_hash(value) -> str:
        if value is None:
            return "null"
        try:
            return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        except TypeError:
            return json.dumps(str(value), ensure_ascii=False)

    @classmethod
    def get_or_create_for_value(cls, value):
        if value in (None, "", [], {}, ()):
            return None
        normalized = cls._normalize_for_hash(value)
        payload_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        obj, _ = cls.objects.get_or_create(hash=payload_hash, defaults={"data": value})
        return obj
