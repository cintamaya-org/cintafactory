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
        .Next(this.nvdossier)
    )

    nvdossier = (
        flow.View(views.UpdateProcessView.as_view(form_class=DATAssignForm))
        .Annotation(title="Nouveau dossier (DAT)")
        .Permission(auto_create=True)
        .Next(this.valref)
    )

    valref = (
        flow.View(views.UpdateProcessView.as_view(form_class=DATApproveForm))
        .Annotation(title="Validation du référent")
        .Permission(auto_create=True)
        .Next(this.checkvalref)
    )

    checkvalref = (
        flow.If(act.process.approved)
        .Then(this.split)
        .Else(this.nvdossier)
    )

    split=(
        flow.Split()
        .Next(this.urba)
        .Next(this.docarchi)
    )

    urba = (
        flow.View(views.UpdateProcessView.as_view(fields=["text"]))
        .Annotation(title="Instruction urbanisme")
        .Permission(auto_create=True)

    )

    docarchi = (
        flow.View(views.UpdateProcessView.as_view(fields=["text"]))
        .Annotation(title="Documentation architecture technique")
        .Permission(auto_create=True)
        .Next(this.arisque)
    )

    arisque = (
        flow.View(views.UpdateProcessView.as_view(fields=["text"]))
        .Annotation(title="Analyse de risque")
        .Permission(auto_create=True)
        .Next(this.precosecu)
    )

    precosecu = (
        flow.View(views.UpdateProcessView.as_view(form_class=DATApproveForm))
        .Annotation(title="Recommendation sécurité")
        .Permission(auto_create=True)
        .Next(this.checkprecosecu)
    )

    checkprecosecu = (
        flow.If(act.process.approved)
        .Then(this.archiprete)
        .Else(this.deropssi)
    )

    archiprete = (
        flow.View(views.UpdateProcessView.as_view(fields=["text"]))
        .Annotation(title="Architecture prête")
        .Permission(auto_create=True)
        .Next(this.split2)
    )

    split2 =(
        flow.Split()
        .Next(this.IOS)
        .Next(this.valcapa)
        .Next(this.cartoflux)
    )

    deropssi = (
        flow.View(views.UpdateProcessView.as_view(form_class=DATApproveForm))
        .Annotation(title="Dérogation à la pssi")
        .Permission(auto_create=True)
        .Next(this.checkderopssi)
    )

    checkderopssi = (
        flow.If(act.process.approved)
        .Then(this.archiprete)
        .Else(this.docarchi)
    )

    IOS = (
        flow.View(views.UpdateProcessView.as_view(fields=["text"]))
        .Annotation(title="Inscription offres de service")
        .Permission(auto_create=True)
        .Next(this.join)
    )

    valcapa = (
        flow.View(views.UpdateProcessView.as_view(fields=["text"]))
        .Annotation(title="Validation capacitaire")
        .Permission(auto_create=True)
        .Next(this.join)
    )

    cartoflux = (
        flow.View(views.UpdateProcessView.as_view(fields=["text"]))
        .Annotation(title="Cartographie des flux")
        .Permission(auto_create=True)
        .Next(this.join)
    )

    join = (
        flow.Join()
        .Next(this.valinfra)
    )

    valinfra = (
        flow.View(views.UpdateProcessView.as_view(form_class=DATApproveForm))
        .Annotation(title="Validation de l'infra")
        .Permission(auto_create=True)
        .Next(this.checkvalinfra)
    )

    checkvalinfra = (
        flow.If(act.process.approved)
        .Then(this.datval)
        .Else(this.archiprete)
    )

    datval = (
        flow.View(views.UpdateProcessView.as_view(fields=["text"]))
        .Annotation(title="Validation du DAT")
        .Permission(auto_create=True)
        .Next(this.pres)
    )

    pres = (
        flow.View(views.UpdateProcessView.as_view(form_class=DATApproveForm))
        .Annotation(title="Présentation en comité")
        .Permission(auto_create=True)
        .Next(this.checkpres)
    )

    checkpres = (
        flow.If(act.process.approved)
        .Then(this.datfinal)
        .Else(this.leveres)
    )

    datfinal = (
        flow.View(views.UpdateProcessView.as_view(fields=["text"]))
        .Annotation(title="DAT final")
        .Permission(auto_create=True)
        .Next(this.end)
    )

    leveres = (
        flow.View(views.UpdateProcessView.as_view(fields=["text"]))
        .Annotation(title="Levé de réserve")
        .Permission(auto_create=True)
    )

    end = flow.End()

    def send_dat_request(self, act):
        print(act.process.text)