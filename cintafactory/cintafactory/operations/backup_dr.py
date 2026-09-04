from __future__ import annotations

import time
from collections import OrderedDict
from typing import Any
from uuid import uuid4

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import connection
from django.utils import timezone

from ..storage.seaweedfs_storage import SeaweedFSStorage
from .slo_baseline import emit_baseline_metric


_PG_SETTING_QUERIES = {
    "archive_mode": "SHOW archive_mode",
    "archive_command": "SHOW archive_command",
    "wal_level": "SHOW wal_level",
}


def _read_pg_setting(name: str) -> str:
    query = _PG_SETTING_QUERIES.get(name)
    if query is None:
        raise ValueError(f"Unsupported PostgreSQL setting: {name}")
    with connection.cursor() as cursor:
        cursor.execute(query)
        row = cursor.fetchone()
    if not row:
        return ""
    return str(row[0] or "").strip()


def _create_restore_point(label: str) -> str:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_create_restore_point(%s)", [label])
        row = cursor.fetchone()
    return str((row or [""])[0] or "")


def collect_postgres_pitr_validation(
    *,
    attempt_restore_point: bool = False,
    require_restore_point: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    payload: dict[str, Any] = {
        "service": "postgres",
        "ok": False,
        "checks": {},
        "errors": [],
    }
    try:
        if connection.vendor != "postgresql":
            payload["errors"].append("Database engine is not PostgreSQL.")
            return payload

        archive_mode = _read_pg_setting("archive_mode").lower()
        archive_command = _read_pg_setting("archive_command")
        wal_level = _read_pg_setting("wal_level").lower()
        payload["checks"] = {
            "archive_mode": archive_mode,
            "archive_command_set": bool(archive_command and archive_command not in {"(disabled)", "false"}),
            "wal_level": wal_level,
            "wal_level_ok": wal_level in {"replica", "logical"},
        }
        if archive_mode != "on":
            payload["errors"].append("archive_mode is not enabled.")
        if not payload["checks"]["archive_command_set"]:
            payload["errors"].append("archive_command is not configured.")
        if not payload["checks"]["wal_level_ok"]:
            payload["errors"].append("wal_level must be replica or logical for PITR.")

        if attempt_restore_point:
            label = f"cinta_dr_probe_{timezone.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
            try:
                restore_point = _create_restore_point(label)
                payload["checks"]["restore_point_created"] = bool(restore_point)
                payload["checks"]["restore_point_name"] = restore_point
                if require_restore_point and not restore_point:
                    payload["errors"].append("Restore point verification returned empty result.")
            except Exception as exc:
                payload["checks"]["restore_point_created"] = False
                payload["checks"]["restore_point_error"] = f"{type(exc).__name__}: {exc}"
                if require_restore_point:
                    payload["errors"].append("Restore point verification failed.")
        payload["ok"] = len(payload["errors"]) == 0
        return payload
    finally:
        emit_baseline_metric(
            "dr.postgres.pitr.validation",
            duration_ms=(time.perf_counter() - started) * 1000.0,
            success=bool(payload.get("ok", False)),
            dimensions={"outcome": "ok" if payload.get("ok", False) else "failed"},
        )


def _collect_storage_references(sample_size: int) -> list[str]:
    from dat.models import DATSectionAttachment
    from diagrams.models import DrawIODiagram, LikeC4Diagram

    limit = max(int(sample_size), 1)
    paths: OrderedDict[str, None] = OrderedDict()

    for path in LikeC4Diagram.objects.order_by("-updated_at").values_list("storage_path", flat=True)[:limit]:
        if path:
            paths[str(path)] = None
    for path in LikeC4Diagram.objects.order_by("-updated_at").values_list("png_path", flat=True)[:limit]:
        if path:
            paths[str(path)] = None
    for batch in LikeC4Diagram.objects.order_by("-updated_at").values_list("png_paths", flat=True)[:limit]:
        if isinstance(batch, list):
            for item in batch:
                if isinstance(item, str) and item:
                    paths[item] = None
    for path in DrawIODiagram.objects.order_by("-updated_at").values_list("xml_file", flat=True)[:limit]:
        if path:
            paths[str(path)] = None
    for path in DrawIODiagram.objects.order_by("-updated_at").values_list("thumbnail", flat=True)[:limit]:
        if path:
            paths[str(path)] = None
    for path in DATSectionAttachment.objects.order_by("-created_at").values_list("storage_path", flat=True)[:limit]:
        if path:
            paths[str(path)] = None

    return list(paths.keys())[:limit]


def _run_storage_probe(storage: SeaweedFSStorage) -> dict[str, Any]:
    probe_name = f"dr/probes/{timezone.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}.txt"
    content = ContentFile(timezone.now().isoformat().encode("utf-8"))
    storage.save(probe_name, content)
    exists = bool(storage.exists(probe_name))
    storage.delete(probe_name)
    return {"probe_path": probe_name, "probe_exists_after_save": exists}


def collect_seaweedfs_backup_validation(
    *,
    sample_size: int = 50,
    write_probe: bool = False,
) -> dict[str, Any]:
    started = time.perf_counter()
    payload: dict[str, Any] = {
        "service": "seaweedfs",
        "ok": False,
        "checks": {},
        "errors": [],
    }
    try:
        references = _collect_storage_references(sample_size)
        storage = SeaweedFSStorage()
        missing: list[str] = []
        checked = 0
        for path in references:
            checked += 1
            try:
                if not storage.exists(path):
                    missing.append(path)
            except Exception:
                missing.append(path)

        payload["checks"] = {
            "sample_size": int(sample_size),
            "checked_paths": checked,
            "missing_paths": missing,
            "missing_count": len(missing),
        }
        if missing:
            payload["errors"].append(f"Missing {len(missing)} storage objects in validation sample.")

        if write_probe:
            try:
                probe = _run_storage_probe(storage)
                payload["checks"]["write_probe"] = probe
                if not probe.get("probe_exists_after_save", False):
                    payload["errors"].append("Storage write/read/delete probe failed.")
            except Exception as exc:
                payload["checks"]["write_probe"] = {"probe_error": f"{type(exc).__name__}: {exc}"}
                payload["errors"].append("Storage write/read/delete probe failed.")

        payload["ok"] = len(payload["errors"]) == 0
        return payload
    finally:
        emit_baseline_metric(
            "dr.seaweedfs.backup.validation",
            duration_ms=(time.perf_counter() - started) * 1000.0,
            success=bool(payload.get("ok", False)),
            dimensions={"outcome": "ok" if payload.get("ok", False) else "failed"},
        )


def run_backup_dr_validation(
    *,
    sample_size: int = 50,
    validate_postgres: bool = True,
    validate_seaweedfs: bool = True,
    write_storage_probe: bool = False,
    attempt_restore_point: bool = False,
    require_restore_point: bool = False,
) -> dict[str, Any]:
    checks: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    if validate_postgres:
        postgres = collect_postgres_pitr_validation(
            attempt_restore_point=attempt_restore_point,
            require_restore_point=require_restore_point,
        )
        checks["postgres"] = postgres
        errors.extend([f"postgres: {item}" for item in postgres.get("errors", [])])

    if validate_seaweedfs:
        seaweed = collect_seaweedfs_backup_validation(sample_size=sample_size, write_probe=write_storage_probe)
        checks["seaweedfs"] = seaweed
        errors.extend([f"seaweedfs: {item}" for item in seaweed.get("errors", [])])

    return {
        "ok": len(errors) == 0,
        "checks": checks,
        "errors": errors,
    }
