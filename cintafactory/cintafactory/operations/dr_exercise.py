from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.utils import timezone

from .alerting import evaluate_runtime_alerts
from .backup_dr import run_backup_dr_validation


@dataclass(frozen=True)
class RecoveryObjective:
    target: float
    actual: float

    @property
    def ok(self) -> bool:
        return self.actual <= self.target

    @property
    def gap(self) -> float:
        return round(max(0.0, self.actual - self.target), 6)


def run_dr_game_day_exercise(
    *,
    postgres_restore_seconds: float,
    seaweedfs_restore_seconds: float,
    data_loss_minutes: float,
    run_dependency_validation: bool = True,
    target_rto_seconds: float | None = None,
    target_rpo_minutes: float | None = None,
) -> dict[str, Any]:
    target_rto = float(target_rto_seconds or getattr(settings, "DR_TARGET_RTO_SECONDS", 3600))
    target_rpo = float(target_rpo_minutes or getattr(settings, "DR_TARGET_RPO_MINUTES", 15))
    measured_rto = max(float(postgres_restore_seconds), float(seaweedfs_restore_seconds))
    measured_rpo = max(0.0, float(data_loss_minutes))

    rto = RecoveryObjective(target=target_rto, actual=measured_rto)
    rpo = RecoveryObjective(target=target_rpo, actual=measured_rpo)

    validation: dict[str, Any] | None = None
    if run_dependency_validation:
        validation = run_backup_dr_validation(
            sample_size=50,
            validate_postgres=True,
            validate_seaweedfs=True,
            write_storage_probe=True,
            attempt_restore_point=True,
            require_restore_point=False,
        )

    alert_evaluation_error = ""
    try:
        active_alerts = evaluate_runtime_alerts()
    except Exception as exc:
        active_alerts = []
        alert_evaluation_error = f"{type(exc).__name__}: {exc}"
    alerts_for_playbook = sorted({item.code for item in active_alerts})

    gaps: list[str] = []
    if not rto.ok:
        gaps.append(
            f"RTO gap: measured={rto.actual:.3f}s target={rto.target:.3f}s gap={rto.gap:.3f}s."
        )
    if not rpo.ok:
        gaps.append(
            f"RPO gap: measured={rpo.actual:.3f}m target={rpo.target:.3f}m gap={rpo.gap:.3f}m."
        )
    if validation and not validation.get("ok", False):
        gaps.append("Backup/restore validation reported failures; see validation.errors.")
    if alert_evaluation_error:
        gaps.append("Alert evaluation unavailable during drill; review playbook linkage manually.")

    recommendations: list[str] = []
    if not rto.ok:
        recommendations.append("Reduce restore execution time or increase automation for critical services.")
    if not rpo.ok:
        recommendations.append("Tighten backup cadence or improve WAL/object replication lag controls.")
    if validation and not validation.get("ok", False):
        recommendations.append("Resolve failing backup checks before accepting DR readiness.")
    if not alerts_for_playbook:
        recommendations.append("Run controlled fault injections to verify alert-playbook linkage in game day.")
    if alert_evaluation_error:
        recommendations.append("Fix alert data-source readiness (migrations/dependencies) before final closure.")

    return {
        "ok": len(gaps) == 0,
        "exercise": {
            "name": "plan5_step5_game_day",
            "executed_at": timezone.now().isoformat(),
        },
        "objectives": {
            "rto_seconds": {
                "target": rto.target,
                "actual": rto.actual,
                "ok": rto.ok,
                "gap": rto.gap,
            },
            "rpo_minutes": {
                "target": rpo.target,
                "actual": rpo.actual,
                "ok": rpo.ok,
                "gap": rpo.gap,
            },
        },
        "validation": validation,
        "alerts_referenced": alerts_for_playbook,
        "alert_evaluation_error": alert_evaluation_error,
        "gaps": gaps,
        "recommendations": recommendations,
    }
