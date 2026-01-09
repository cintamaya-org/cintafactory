from __future__ import annotations

import logging

from django.core.exceptions import ImproperlyConfigured
from django.template.loader import render_to_string

from .exporters import get_dat_export_model_builder

logger = logging.getLogger(__name__)


def generate_dat_pdf(dat, *, base_url: str | None = None):
    """
    Build the DAT export payload and render it as a PDF document.
    """
    reference = getattr(dat, "reference", None) or getattr(dat, "title", None) or f"DAT #{dat.pk}"
    print(f"[DAT PDF] generation demarree ({reference}).", flush=True)
    logger.info("Generation PDF DAT demarree (%s).", reference)
    builder = get_dat_export_model_builder()
    payload = builder.build(dat)
    sections = payload.get("sections") or []
    sub_section_count = 0
    part_count = 0
    for section in sections:
        if not isinstance(section, dict):
            continue
        sub_sections = section.get("sub_sections") or []
        sub_section_count += len(sub_sections)
        for sub_section in sub_sections:
            if not isinstance(sub_section, dict):
                continue
            part_count += len(sub_section.get("parts") or [])
    logger.info(
        "Export PDF DAT %s: %s participants, %s sections, %s sous-sections, %s parties.",
        reference,
        len(payload.get("participants") or []),
        len(sections),
        sub_section_count,
        part_count,
    )
    html = render_to_string(
        "dat/exports/dat_export_pdf.html",
        {
            "dat": dat,
            "export": payload,
        },
    )
    print(f"[DAT PDF] HTML genere ({len(html)} caracteres).", flush=True)
    logger.debug("HTML PDF DAT %s genere (%s caracteres).", reference, len(html))
    pdf_content = render_pdf_from_html(html, base_url=base_url)
    print(f"[DAT PDF] PDF genere ({len(pdf_content)} octets).", flush=True)
    logger.info("PDF DAT %s genere (%s octets).", reference, len(pdf_content))
    return pdf_content, payload


def render_pdf_from_html(html: str, *, base_url: str | None = None) -> bytes:
    logger.debug("Rendu PDF WeasyPrint (base_url=%s).", base_url)
    try:
        from weasyprint import HTML
    except ImportError as exc:  # pragma: no cover - env misconfiguration
        raise ImproperlyConfigured(
            "Le module WeasyPrint doit être installé pour permettre l'export PDF des DAT."
        ) from exc
    return HTML(string=html, base_url=base_url).write_pdf()
