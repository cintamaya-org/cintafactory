from django.db import models

# Create your models here.

from django.db import models
from django.utils.translation import gettext_lazy as _
from viewflow import jsonstore
from viewflow.workflow.models import Process
from django import forms

class Person(models.Model):
    
    PersonID = models.CharField(max_length = 20, unique = True)
    name = models.CharField(max_length=200)

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

    actif = models.BooleanField(default=True)
    # département / entité de rattachement
    dept = models.CharField(max_length=100, default="Non précisé")
    email = models.EmailField

    def __str__(self):
        return self.PersonID + " " + self.name
    
class AppStatus(models.TextChoices):
    ARRET = "ART", _("Arrêtée")
    DECOM = "DEC", _("Décommissionnée")
    ENPROD = "PRD", _("En Production")
    PILOTE = "PLT", ("En phase pilote")
    ABANDON = "ABD", _("Abandonnée")
    ENREAL = "REL", _("En réalisation")
    ETUDE = "ETD", _("En cours d'étude")
    PROP = "PRP", _("Proposé en cible")
    
class CritLvl(models.TextChoices):
    STANDARD = "STD", _("Standard")
    SENSIBLE = "SEN", _("Sensible")
    CRITIQUE = "CRT", _("Critique")
    EXPERIMENTAL = "EXP", _("Expérimentation")
    
class Application(models.Model):

    ApplicationID = models.CharField(max_length=5, unique = True)
    name = models.CharField(max_length=100)
    UrbaID = models.CharField(max_length=8, default="00000")
    # Trigramme = models.CharField(max_length=3, unique=False, default="NNN")
    Description = models.CharField(max_length=100, default="description de la finalité de l'application")
    EtatOperationnel = models.CharField(choices=AppStatus, default="PRD")
    Exploitant = models.CharField(max_length=50, default="CDS Exploitation")
    Criticite = models.CharField(choices=CritLvl, default="STD")
    # Acteurs
    cdp = Person # Chef de projet
    pdd = Person # Porteur de la demande 
    LS = models.BooleanField(default=False) # vrai si cette appli est une ligne de service

    def __str__(self):
        return self.ApplicationID

class Environnement(models.Model):
    EnvID = models.AutoField,
    # paramètre à personnaliser selon le client :
    # coté SNCF, la préprod est Hors prod, la Formation est Prod
    class EnvChoices(models.TextChoices):
        PRODUCTION = "PRD", _("Production")
        PREPRODUCTION = "PPD", _("Pré-production")
        PRA = "PRA", _("PRA")
        PPR = "PPR", _("Préprod PRA")
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

class Standardisation(models.TextChoices):
    STANDARD = "STD", _("Standard")
    DEROGATOIRE = "DRG", _("Dérogatoire")
    SPECIFIQUE = "SPC", _("Spécifique")
    PATRIMONIAL = "PTR", _("Patrimonial")
    OBSOLETE = "OBS", _("Obsolète")
    
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
    
class ComposantLogiciel(models.Model):
    from .models import Standardisation
    CLID = models.AutoField
    CLName = models.CharField(max_length=50, default=" ")
    # Description complémentaire
    CLDesc = models.CharField(max_length=200, default="Description d'usage du composant logiciel")
    CLStd = Standardisation(value="STD")
    CLProduct = models.CharField(max_length=50, default=" ")
    CLEditor = models.CharField(max_length=50, default=" ")
    # FIXME : 
    # reprendre les licences connues de façon structurée à partir de la base SPDX 
    CLLicence = models.CharField(max_length=50, default=" ")
    OSS = models.BooleanField(default=True)
    Version = models.CharField(max_length=20, default="0.0.0")
    Derogation = models.BooleanField(default=False)
    
    
    def __str__(self):
        return self.CLName
    

class DATProcess(Process):
    text = jsonstore.CharField(max_length=150)
    approved = jsonstore.BooleanField(default=False)

    class Meta:
        proxy = True

    def __str__(self):
        return self.text or f"DATProcess #{self.pk}"

class DATProcessForm(forms.ModelForm):
    class Meta:
        model = DATProcess
        fields = ['text', 'approved']
        labels = {
            'approved': 'Approuvé',
        }