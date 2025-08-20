from django.db import models

# Create your models here.

from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.db.models import Case, Value, When

class Person(models.Model):
    
    PersonID = models.CharField(
        max_length = 20,
        unique = True
    )

    name = models.CharField(
        max_length=200
    )

    class RoleChoices(models.TextChoices):
        ARCHI_REF = "AR", _("Architecte Référent")
        ARCHI_TECH = "AT", _("Architecte Technique")
        ARCHI_LOG = "AL", _("Architecte Logiciel")
        URBA = "UR", _("Urbaniste")
        ANALYSTE_SECU = "AS", _("Analyste Cyber sécurité")
        SSI = "RS", _("Responsable SSI")
        CONSULTATION = "CS", _("Consultation")

    role = models.CharField(
        max_length=2,
        choices = RoleChoices,
        default=RoleChoices.CONSULTATION
    )

    actif = models.BooleanField(
        default=True
    )
    
    # département / entité de rattachement
    dept = models.CharField(max_length=100, default="Non précisé")

    def __str__(self):
        return self.PersonID
    
class Application(models.Model):

    ApplicationID = models.CharField(
        max_length=5,
        unique = True
    )

    name = models.CharField(
        max_length=100,
    )

    UrbaID = models.CharField(
        max_length=8,
        default="00000"
        )

    # Chef de projet
    cdp = Person

    # Porteur de la demande 
    pdd = Person

    def __str__(self):
        return self.ApplicationID

class Environnement(models.Model):
    EnvID = models.AutoField,
    # paramètre à personnaliser selon le client :
    # coté SNCF, la préprod est Hors prod, la Formation est Prod
    class EnvChoices(models.TextChoices):
        PRODUCTION = "PRD", _("Production")
        PREPRODUCTION = "PPD", _("Pré-production")
        FORMATION = "FRM", _("Formation")
        INTEGRATION = "INT", _("Intégration")
        RECETTE = "RCT", _("Recette")
        QUALIF = "QLF", _("Qualification")

    EnvName = models.CharField(
        max_length=3,
        choices = EnvChoices,
        default=EnvChoices.PRODUCTION
    )

    IsPROD = models.BooleanField(
        default=True
    )

    def save(self, **kwargs):
        return     super().save(**kwargs)
    
    


class DAT(models.Model):
    DAT_id = models.CharField(
        max_length=10,
        unique=True
        )
    Appli = Application
    Date_Creation = models.DateField(auto_now_add=True)
    Date_MAJ = models.DateField(auto_now=True)
    Version = models.CharField(10)

    ## Documents associés au DAT
    # peuvent être multiples
    DocRef = models.URLField

    def __str__(self):
        return self.DAT_id