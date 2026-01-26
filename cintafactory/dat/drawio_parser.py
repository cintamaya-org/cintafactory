from __future__ import annotations

import base64
import html
import logging
import zlib
from typing import Dict, Iterable, List, Tuple
from urllib.parse import unquote
from defusedxml import ElementTree as DefusedElementTree


logger = logging.getLogger(__name__)

MAX_XML_CHARS = 8_000_000
MAX_INFLATED_BYTES = 8_000_000

BRIQUE_COLUMNS = ("brique_id", "nom", "description")
FLUX_COLUMNS = (
    "statut",
    "flux_id",
    "source",
    "cible",
    "protocole",
    "port",
    "chiffrement",
    "authentification",
)


def _strip_namespace(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _clean_model_xml(payload: str) -> str | None:
    if not payload:
        return None
    candidate = payload.strip()
    if not candidate:
        return None
    if len(candidate) > MAX_XML_CHARS:
        logger.debug("drawio parser: payload exceeds max size (%s chars)", len(candidate))
        return None
    for transform in (lambda value: value, html.unescape, unquote):
        try:
            transformed = transform(candidate)
        except Exception:
            continue
        if not transformed:
            continue
        if len(transformed) > MAX_XML_CHARS:
            continue
        if transformed.lstrip().startswith("<mxGraphModel"):
            return transformed.strip()
        index = transformed.find("<mxGraphModel")
        if index != -1:
            return transformed[index:].strip()
    return None


def _inflate_drawio_payload(encoded: str) -> str | None:
    if not encoded:
        return None
    try:
        raw = base64.b64decode(encoded)
    except Exception:
        return None
    for wbits in (-15, zlib.MAX_WBITS):
        try:
            decompressor = zlib.decompressobj(wbits)
            inflated = decompressor.decompress(raw, MAX_INFLATED_BYTES + 1)
        except Exception:
            continue
        if len(inflated) > MAX_INFLATED_BYTES or not decompressor.eof:
            continue
        try:
            decoded = inflated.decode("utf-8", errors="ignore")
        except Exception:
            decoded = ""
        if not decoded:
            continue
        cleaned = _clean_model_xml(unquote(decoded))
        if cleaned:
            return cleaned
    return None


def _extract_mxgraph_models(xml_payload: str) -> List[str]:
    if not xml_payload or not isinstance(xml_payload, str):
        return []
    content = xml_payload.strip()
    if not content:
        return []
    if len(content) > MAX_XML_CHARS:
        logger.debug("drawio parser: xml payload exceeds max size (%s chars)", len(content))
        return []
    try:
        root = DefusedElementTree.fromstring(content)
    except DefusedElementTree.ParseError:
        return []
    tag = _strip_namespace(root.tag)
    if tag == "mxGraphModel":
        return [content]
    if tag != "mxfile":
        return []
    models: List[str] = []
    for diagram in root.iter():
        if _strip_namespace(diagram.tag) != "diagram":
            continue
        raw_payload = (diagram.text or "").strip()
        if raw_payload:
            cleaned = _clean_model_xml(raw_payload) or _inflate_drawio_payload(raw_payload)
            if cleaned:
                models.append(cleaned)
                continue
        for child in diagram:
            if _strip_namespace(child.tag) != "mxGraphModel":
                continue
            models.append(DefusedElementTree.tostring(child, encoding="unicode"))
            break
    return models


def extract_drawio_pages(xml_payload: str) -> List[Dict[str, str]]:
    if not xml_payload or not isinstance(xml_payload, str):
        return []
    content = xml_payload.strip()
    if not content:
        return []
    if len(content) > MAX_XML_CHARS:
        logger.debug("drawio parser: xml payload exceeds max size (%s chars)", len(content))
        return []
    try:
        root = DefusedElementTree.fromstring(content)
    except DefusedElementTree.ParseError:
        return []
    tag = _strip_namespace(root.tag)
    if tag == "mxGraphModel":
        return [{"index": 0, "name": "Page 1", "xml": content}]
    if tag != "mxfile":
        return []
    pages: List[Dict[str, str]] = []
    index = 0
    for diagram in root.iter():
        if _strip_namespace(diagram.tag) != "diagram":
            continue
        name = diagram.get("name") or diagram.get("label") or f"Page {index + 1}"
        raw_payload = (diagram.text or "").strip()
        page_xml = ""
        if raw_payload:
            page_xml = _clean_model_xml(raw_payload) or _inflate_drawio_payload(raw_payload) or ""
        if not page_xml:
            for child in diagram:
                if _strip_namespace(child.tag) != "mxGraphModel":
                    continue
                page_xml = DefusedElementTree.tostring(child, encoding="unicode")
                break
        if page_xml:
            pages.append({"index": index, "name": name, "xml": page_xml})
        index += 1
    return pages


def _iter_drawio_objects(model_xml: str) -> Iterable[Dict[str, str]]:
    if not model_xml:
        return []
    if len(model_xml) > MAX_XML_CHARS:
        logger.debug("drawio parser: model xml exceeds max size (%s chars)", len(model_xml))
        return []
    try:
        root = DefusedElementTree.fromstring(model_xml)
    except DefusedElementTree.ParseError as exc:
        logger.debug("drawio parser: invalid xml: %s", exc)
        return []
    objects: List[Dict[str, str]] = []
    for element in root.iter():
        if _strip_namespace(element.tag) != "object":
            continue
        attrs = {key.lower(): value for key, value in element.attrib.items()}
        source = attrs.get("source") or ""
        target = attrs.get("target") or ""
        if not source or not target:
            for child in element:
                if _strip_namespace(child.tag) != "mxCell":
                    continue
                source = source or child.attrib.get("source") or ""
                target = target or child.attrib.get("target") or ""
                break
        attrs["source"] = source
        attrs["target"] = target
        objects.append(attrs)
    return objects


def _build_brique_row(attrs: Dict[str, str]) -> Dict[str, str]:
    row = {key: "" for key in BRIQUE_COLUMNS}
    row["brique_id"] = attrs.get("idbrique") or ""
    row["nom"] = attrs.get("labelbrique") or ""
    row["description"] = attrs.get("commentaire") or attrs.get("description") or ""
    return row


def _build_flux_row(attrs: Dict[str, str], object_index: Dict[str, Dict[str, str]]) -> Dict[str, str]:
    row = {key: "" for key in FLUX_COLUMNS}
    row["flux_id"] = attrs.get("idflux") or ""
    row["port"] = attrs.get("port") or ""
    protocole = attrs.get("protocole") or ""
    row["protocole"] = protocole
    protocole_norm = protocole.strip().lower()
    if protocole_norm == "https":
        row["chiffrement"] = "oui"
    elif protocole_norm == "http":
        row["chiffrement"] = "non"
    mecanisme_auth = (attrs.get("mecanismeauth") or "").strip().lower()
    if mecanisme_auth == "certificat":
        row["authentification"] = "oui"
    source_id = attrs.get("source") or ""
    target_id = attrs.get("target") or ""
    source_obj = object_index.get(source_id, {})
    target_obj = object_index.get(target_id, {})
    row["source"] = source_obj.get("labelbrique") or source_obj.get("idbrique") or ""
    row["cible"] = target_obj.get("labelbrique") or target_obj.get("idbrique") or ""
    return row


def _merge_rows(existing: Dict[str, str], incoming: Dict[str, str], columns: Iterable[str]) -> Dict[str, str]:
    merged = dict(existing)
    for column in columns:
        current = merged.get(column) or ""
        if current:
            continue
        candidate = incoming.get(column) or ""
        if candidate:
            merged[column] = candidate
    return merged


def _brique_key(row: Dict[str, str]) -> tuple:
    brique_id = (row.get("brique_id") or "").strip().lower()
    if brique_id:
        return ("id", brique_id)
    nom = (row.get("nom") or "").strip().lower()
    if nom:
        return ("nom", nom)
    description = (row.get("description") or "").strip().lower()
    if description:
        return ("desc", description)
    return ("row", "")


def _flux_key(row: Dict[str, str]) -> tuple:
    flux_id = (row.get("flux_id") or "").strip().lower()
    if flux_id:
        return ("id", flux_id)
    source = (row.get("source") or "").strip().lower()
    cible = (row.get("cible") or "").strip().lower()
    protocole = (row.get("protocole") or "").strip().lower()
    port = (row.get("port") or "").strip().lower()
    if source or cible or protocole or port:
        return ("tuple", source, cible, protocole, port)
    return ("row", "")


def _dedupe_rows(
    rows: List[Dict[str, str]], columns: Iterable[str], key_fn
) -> List[Dict[str, str]]:
    deduped: List[Dict[str, str]] = []
    index: Dict[tuple, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = key_fn(row)
        if key in index:
            existing_index = index[key]
            deduped[existing_index] = _merge_rows(deduped[existing_index], row, columns)
            continue
        index[key] = len(deduped)
        deduped.append(dict(row))
    return deduped


def dedupe_architecture_rows(
    briques: List[Dict[str, str]], fluxes: List[Dict[str, str]]
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    return (
        _dedupe_rows(briques, BRIQUE_COLUMNS, _brique_key),
        _dedupe_rows(fluxes, FLUX_COLUMNS, _flux_key),
    )


def parse_architecture_diagram(xml_payload: str) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    briques: List[Dict[str, str]] = []
    fluxes: List[Dict[str, str]] = []
    for model_xml in _extract_mxgraph_models(xml_payload):
        objects = list(_iter_drawio_objects(model_xml))
        if not objects:
            continue
        object_index = {obj.get("id", ""): obj for obj in objects if obj.get("id")}
        for obj in objects:
            object_type = (obj.get("objecttype") or "").strip().lower()
            if object_type == "brique":
                briques.append(_build_brique_row(obj))
            elif object_type == "flux":
                fluxes.append(_build_flux_row(obj, object_index))
    return dedupe_architecture_rows(briques, fluxes)
