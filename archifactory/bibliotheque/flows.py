from viewflow import this
from viewflow.workflow import flow, act
from viewflow.workflow.flow import views

from bibliotheque.models import DATProcess, DATApproveForm, DATAssignForm


class DATFlow(flow.Flow):
    process_class = DATProcess

    def get_task_title(self, task):
        return task.process.text or f"DAT #{task.process.pk}"

    start = (
        flow.Start(views.CreateProcessView.as_view(fields=["text"]))
        .Annotation(title="Nouveau besoin (DAL)")
        .Permission(auto_create=True)
        .Next(this.NouveauDossier)
    )

    NouveauDossier = (
        flow.View(views.UpdateProcessView.as_view(form_class=DATAssignForm))
        .Annotation(title="Nouveau dossier (DAT)")
        .Permission(auto_create=True)
        .Next(this.ValidationReferent)
    )

    ValidationReferent = (
        flow.View(views.UpdateProcessView.as_view(form_class=DATApproveForm))
        .Annotation(title="Validation du référent")
        .Permission(auto_create=True)
        .Next(this.VerificationValidationReferent)
    )

    VerificationValidationReferent = (
        flow.If(act.process.approved)
        .Then(this.split)
        .Else(this.NouveauDossier)
    )

    split=(
        flow.Split()
        .Next(this.InstructionUrbanistes)
        .Next(this.DocumentationArchitectureTechnique)
    )

    InstructionUrbanistes = (
        flow.View(views.UpdateProcessView.as_view(fields=["text"]))
        .Annotation(title="Instruction urbanisme")
        .Permission(auto_create=True)

    )

    DocumentationArchitectureTechnique = (
        flow.View(views.UpdateProcessView.as_view(fields=["text"]))
        .Annotation(title="Documentation architecture technique")
        .Permission(auto_create=True)
        .Next(this.AnalyseRisques)
    )

    AnalyseRisques = (
        flow.View(views.UpdateProcessView.as_view(fields=["text"]))
        .Annotation(title="Analyse de risque")
        .Permission(auto_create=True)
        .Next(this.PreconisationSecurite)
    )

    PreconisationSecurite = (
        flow.View(views.UpdateProcessView.as_view(form_class=DATApproveForm))
        .Annotation(title="Recommendation sécurité")
        .Permission(auto_create=True)
        .Next(this.ValidationPreconisationSecurite)
    )

    ValidationPreconisationSecurite = (
        flow.If(act.process.approved)
        .Then(this.ArchitecturePrete)
        .Else(this.DerogationPSSI)
    )

    ArchitecturePrete = (
        flow.View(views.UpdateProcessView.as_view(fields=["text"]))
        .Annotation(title="Architecture prête")
        .Permission(auto_create=True)
        .Next(this.split2)
    )

    split2 =(
        flow.Split()
        .Next(this.InscriptionOffresService)
        .Next(this.ValidationCapacitaire)
        .Next(this.PublicationCartographieFlux)
    )

    DerogationPSSI = (
        flow.View(views.UpdateProcessView.as_view(form_class=DATApproveForm))
        .Annotation(title="Dérogation à la pssi")
        .Permission(auto_create=True)
        .Next(this.ValidationDerogationPSSI)
    )

    ValidationDerogationPSSI = (
        flow.If(act.process.approved)
        .Then(this.ArchitecturePrete)
        .Else(this.DocumentationArchitectureTechnique)
    )

    InscriptionOffresService = (
        flow.View(views.UpdateProcessView.as_view(fields=["text"]))
        .Annotation(title="Inscription offres de service")
        .Permission(auto_create=True)
        .Next(this.join)
    )

    ValidationCapacitaire = (
        flow.View(views.UpdateProcessView.as_view(fields=["text"]))
        .Annotation(title="Validation capacitaire")
        .Permission(auto_create=True)
        .Next(this.join)
    )

    PublicationCartographieFlux = (
        flow.View(views.UpdateProcessView.as_view(fields=["text"]))
        .Annotation(title="Cartographie des flux")
        .Permission(auto_create=True)
        .Next(this.join)
    )

    join = (
        flow.Join()
        .Next(this.ValidationInfrastructureExploitation)
    )

    ValidationInfrastructureExploitation = (
        flow.View(views.UpdateProcessView.as_view(form_class=DATApproveForm))
        .Annotation(title="Validation de l'infra")
        .Permission(auto_create=True)
        .Next(this.ValidationValidationInfrastructureExploitation)
    )

    ValidationValidationInfrastructureExploitation = (
        flow.If(act.process.approved)
        .Then(this.DATValide)
        .Else(this.ArchitecturePrete)
    )

    DATValide = (
        flow.View(views.UpdateProcessView.as_view(fields=["text"]))
        .Annotation(title="Validation du DAT")
        .Permission(auto_create=True)
        .Next(this.PresentationComite)
    )

    PresentationComite = (
        flow.View(views.UpdateProcessView.as_view(form_class=DATApproveForm))
        .Annotation(title="Présentation en comité")
        .Permission(auto_create=True)
        .Next(this.ValidationPresentationComite)
    )

    ValidationPresentationComite = (
        flow.If(act.process.approved)
        .Then(this.DATPublie)
        .Else(this.LeveReserve)
    )

    DATPublie = (
        flow.View(views.UpdateProcessView.as_view(fields=["text"]))
        .Annotation(title="DAT final")
        .Permission(auto_create=True)
        .Next(this.end)
    )

    LeveReserve = (
        flow.View(views.UpdateProcessView.as_view(fields=["text"]))
        .Annotation(title="Levé de réserve")
        .Permission(auto_create=True)
    )

    end = flow.End()

    def send_dat_request(self, act):
        print(act.process.text)