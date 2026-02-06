from __future__ import annotations

try:
    from viewflow.workflow import flow
    from viewflow import this
    FlowBase = flow.Flow
except Exception:  # pragma: no cover - fallback for legacy viewflow API
    from viewflow import flow, this  # type: ignore
    from viewflow.base import Flow as FlowBase



class DatViewflowFlow(FlowBase):
    # Let Viewflow use its default Process model.
    process_class = getattr(flow, "Process", None) or getattr(flow, "ProcessModel", None)

    if hasattr(flow, "StartHandle"):
        start = flow.StartHandle(this.create_process).Next(this.end)
    elif hasattr(flow, "StartFunction"):
        start = flow.StartFunction(this.create_process).Next(this.end)
    else:  # pragma: no cover - fallback, should not happen for supported viewflow versions
        raise ImportError("Unsupported viewflow version: missing StartHandle/StartFunction")

    end = flow.End()

    def create_process(self, activation, **kwargs):
        activation.prepare()
        dat = kwargs.get("dat")
        dat_id = kwargs.get("dat_id")
        if dat is None and dat_id:
            from dat.models import DAT

            dat = DAT.objects.filter(pk=dat_id).first()
        if dat is not None:
            from .models import DatViewflowProcess

            DatViewflowProcess.objects.get_or_create(
                dat=dat,
                defaults={"process_id": getattr(activation.process, "pk", None)},
            )
        activation.done()
