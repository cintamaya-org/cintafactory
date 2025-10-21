from django.conf import settings
from django.db import models


class DATStatus(models.TextChoices):
    BESOIN_DAL = "besoin_dal", "Nouveau besoin (DAL)"
    NOUVEAU_DOSSIER = "nouveau_dat", "Nouveau dossier (DAT)"
    VALIDATION_REFERENT = "validation_referent", "Validation du referent"
    INSTRUCTION_URBANISME = "instruction_urbanisme", "Instruction urbanisme"
    DOCUMENTATION_TECHNIQUE = "documentation_technique", "Documentation architecture technique"
    ANALYSE_RISQUE = "analyse_risque", "Analyse de risque"
    PRECONISATION_SECURITE = "preconisation_securite", "Preconisation securite"
    DEROGATION_PSSI = "derogation_pssi", "Derogation PSSI"
    ARCHITECTURE_PRETE = "architecture_prete", "Architecture prete"
    INSCRIPTION_OFFRES_SERVICE = "inscription_offres_service", "Inscription offres de service"
    VALIDATION_CAPACITAIRE = "validation_capacitaire", "Validation capacitaire"
    CARTOGRAPHIE_FLUX = "cartographie_flux", "Cartographie des flux"
    VALIDATION_INFRA = "validation_infrastructure", "Validation infrastructure / exploitation"
    DAT_VALIDE = "dat_valide", "DAT valide"
    PRESENTATION_COMITE = "presentation_comite", "Presentation en comite"
    LEVEE_RESERVE = "levee_reserve", "Levee de reserve"
    DAT_PUBLIE = "dat_publie", "DAT publie"


class DAT(models.Model):

    reference = models.CharField(max_length=64, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=64,
        choices=DATStatus.choices,
        default=DATStatus.BESOIN_DAL,
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
        return f"{self.reference} — {self.title}"
