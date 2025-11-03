import base64
import json
from io import BytesIO

from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.files.base import ContentFile
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, TemplateView
from PIL import Image

from .forms import DiagramForm
from .models import Diagram


class DiagramListView(LoginRequiredMixin, ListView):
    template_name = "diagrams/list.html"
    context_object_name = "diagrams"

    def get_queryset(self):
        return Diagram.objects.filter(owner=self.request.user)


class DiagramCreateView(LoginRequiredMixin, CreateView):
    template_name = "diagrams/create.html"
    form_class = DiagramForm

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.owner = self.request.user
        obj.xml = "<mxGraphModel/>"
        obj.save()
        return redirect("diagrams:edit", pk=obj.pk)


class DiagramDetailView(LoginRequiredMixin, DetailView):
    template_name = "diagrams/detail.html"
    model = Diagram

    def get_queryset(self):
        return Diagram.objects.filter(owner=self.request.user)


class DiagramEditView(LoginRequiredMixin, TemplateView):
    template_name = "diagrams/edit.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        diagram = get_object_or_404(Diagram, pk=kwargs["pk"], owner=self.request.user)
        context["diagram"] = diagram
        return context


@login_required
@require_POST
def diagram_save_xml(request, pk: int):
    diagram = get_object_or_404(Diagram, pk=pk, owner=request.user)
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "invalid payload"}, status=400)

    xml = data.get("xml", "")
    if not isinstance(xml, str):
        return JsonResponse({"ok": False, "error": "invalid xml"}, status=400)

    diagram.xml = xml
    diagram.updated_at = timezone.now()
    diagram.save(update_fields=["xml", "updated_at"])
    return JsonResponse({"ok": True})


@login_required
@require_POST
def diagram_save_thumbnail(request, pk: int):
    diagram = get_object_or_404(Diagram, pk=pk, owner=request.user)
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "invalid payload"}, status=400)

    data_uri = data.get("data_uri")
    if not (isinstance(data_uri, str) and data_uri.startswith("data:image/png;base64,")):
        return JsonResponse({"ok": False, "error": "expected PNG data URI"}, status=400)

    b64 = data_uri.split(",", 1)[1]
    raw = base64.b64decode(b64)

    image = Image.open(BytesIO(raw)).convert("RGBA")
    output = BytesIO()
    image.save(output, format="PNG")
    output.seek(0)

    diagram.thumbnail.save("thumb.png", ContentFile(output.read()), save=False)
    diagram.updated_at = timezone.now()
    diagram.save(update_fields=["thumbnail", "updated_at"])

    return JsonResponse({"ok": True, "thumbnail_url": diagram.thumbnail.url})
