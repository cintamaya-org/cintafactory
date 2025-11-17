from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured
from django.template.loader import render_to_string

from .exporters import get_dat_export_model_builder


def generate_dat_pdf(dat, *, base_url: str | None = None):
    """
    Build the DAT export payload and render it as a PDF document.
    """
    builder = get_dat_export_model_builder()
    payload = builder.build(dat)
    html = render_to_string(
        "dat/exports/dat_export_pdf.html",
        {
            "dat": dat,
            "export": payload,
        },
    )
    pdf_content = render_pdf_from_html(html, base_url=base_url)
    return pdf_content, payload


def render_pdf_from_html(html: str, *, base_url: str | None = None) -> bytes:
    try:
        from weasyprint import HTML
    except ImportError as exc:  # pragma: no cover - env misconfiguration
        raise ImproperlyConfigured(
            "Le module WeasyPrint doit être installé pour permettre l'export PDF des DAT."
        ) from exc
    return HTML(string=html, base_url=base_url).write_pdf()
