from django.db import models

# Create your models here.

from users import models as UsersModel
from django.db.models import UniqueConstraint
from django.db.models.functions import Lower

## Static constant

# Etat d'exploitation d'une application
# FIXME - prévoir page spécifique dans l'admin pour la customisation et override 
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

class EnvChoices(models.TextChoices):
    PRODUCTION = "PRD", _("Production")
    PREPRODUCTION = "PPD", _("Pré-production")
    PRA = "PRA", _("PRA")
    PPR = "PPR", _("Préprod PRA")
    FORMATION = "FRM", _("Formation")
    INTEGRATION = "INT", _("Intégration")
    RECETTE = "RCT", _("Recette")
    QUALIF = "QLF", _("Qualification")

class Application(models.Model):
    ApplicationID = models.CharField(max_length=8)
    ApplicationName = models.CharField(max_length=25)
    ApplicationDescription = models.CharField(max_length=100)
    ApplicationTrigramme = models.CharField(max_length=3,unique=True)
    ApplicationStatus = models.CharField(choices=AppStatus, default="PRD")
    ApplicationCriticite = models.CharField(choices=CritLvl, default="STD")
    ApplicationLS = models.BooleanField(default=False) # Vrai pour les lignes de service
    
    # Utilisateurs associés à une application
    # FIXME : ajouter les contraines pour vérifier que l'utilisateur appartient au bon groupe
    ChefDeProjet = UsersModel.User
    ArchiRef = UsersModel.User
    Porteur = UsersModel.User
        
    def __str__(self):
        return self.ApplicationID
    
    def is_LS(self):
        return self.ApplicationLS
    
    class Meta:
        constraints = [
            
        ]
    
class DAT(models.model):
    DATID = models.CharField(max_length=12, unique=True)
    