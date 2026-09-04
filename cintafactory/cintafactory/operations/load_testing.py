from __future__ import annotations

import hashlib
import json
import math
import os
import random
import re
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Callable, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.db import close_old_connections, transaction
from django.db.models import F
from django.db.models.signals import post_delete
from django.utils import timezone

from dat.config.section_blueprints import SECTION_BLUEPRINTS
from dat.models import (
    Application,
    DAT,
    DATAdmin,
    DATHistory,
    DATHistoryAction,
    DATPart,
    DATPartEntry,
    DATPartEntryType,
    DATPartPayload,
    DATParticipant,
    DATParticipantType,
    DATSection,
    DATSectionMetadata,
    DATSectionParticipant,
    DATSectionResponsible,
    DATStatus,
    DATSubSection,
)
from users.models import BusinessDirection, BusinessGroup, Role, TechnicalDirection

from .scaling_validation import LoadSummary, evaluate_slo, percentile_ms


RUN_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,23}$")
LOAD_TEST_PREFIX = "loadtest-"
TRUE_VALUES = {"1", "true", "yes", "on"}
REFERENCE_DIRECTION_COUNT = 4
ROLES_PER_DIRECTION = 2
PAYLOAD_VALUES_PER_TYPE = 16
MAX_LATENCY_SAMPLES = 100_000
MAX_REPORTED_ERRORS = 20
MANIFEST_PREFIX = "LOAD_TEST_MANIFEST:"


class LoadTestError(RuntimeError):
    pass


@dataclass(frozen=True)
class LoadProfile:
    users: int
    applications: int
    dats: int
    fill_ratio: float
    duration: float
    concurrency: int


LOAD_PROFILES: dict[str, LoadProfile] = {
    "small": LoadProfile(100, 25, 250, 0.25, 30.0, 5),
    "medium": LoadProfile(1_000, 250, 5_000, 0.50, 120.0, 20),
    "large": LoadProfile(10_000, 2_500, 50_000, 0.75, 600.0, 50),
}


@dataclass(frozen=True)
class SeedConfig:
    run_id: str
    seed: int
    users: int
    applications: int
    dats: int
    fill_ratio: float
    batch_size: int = 250

    @property
    def prefix(self) -> str:
        return run_prefix(self.run_id)


@dataclass(frozen=True)
class Thresholds:
    max_p95_ms: float | None = None
    max_error_rate: float | None = None
    min_throughput: float | None = None


ProgressCallback = Callable[[str], None]


def run_prefix(run_id: str) -> str:
    validate_run_id(run_id)
    return f"{LOAD_TEST_PREFIX}{run_id}-"


def validate_run_id(run_id: str) -> str:
    value = str(run_id or "").strip().lower()
    if not RUN_ID_RE.fullmatch(value):
        raise LoadTestError("run-id must match [a-z0-9][a-z0-9-]{0,23}")
    return value


def validate_url(value: str) -> str:
    parsed = urlparse(str(value))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise LoadTestError("base-url must be an absolute http(s) URL")
    return str(value).rstrip("/")


def ensure_load_test_allowed(*, allow_non_debug: bool, environ: dict[str, str] | None = None) -> None:
    env = os.environ if environ is None else environ
    if str(env.get("LOAD_TEST_ENABLED", "")).lower() not in TRUE_VALUES:
        raise LoadTestError("LOAD_TEST_ENABLED=1 is required for mutating load-test actions")
    if not settings.DEBUG and not allow_non_debug:
        raise LoadTestError("DEBUG is false; pass --allow-non-debug to confirm this environment")


def resolve_profile(
    profile_name: str,
    *,
    users: int | None = None,
    applications: int | None = None,
    dats: int | None = None,
    fill_ratio: float | None = None,
    duration: float | None = None,
    concurrency: int | None = None,
) -> dict[str, int | float]:
    try:
        profile = LOAD_PROFILES[profile_name]
    except KeyError as exc:
        raise LoadTestError(f"unknown profile: {profile_name}") from exc
    resolved: dict[str, int | float] = {
        "users": profile.users if users is None else int(users),
        "applications": profile.applications if applications is None else int(applications),
        "dats": profile.dats if dats is None else int(dats),
        "fill_ratio": profile.fill_ratio if fill_ratio is None else float(fill_ratio),
        "duration": profile.duration if duration is None else float(duration),
        "concurrency": profile.concurrency if concurrency is None else int(concurrency),
    }
    for name in ("users", "applications", "dats", "concurrency"):
        if int(resolved[name]) < 1:
            raise LoadTestError(f"{name} must be >= 1")
    if not 0.0 <= float(resolved["fill_ratio"]) <= 1.0:
        raise LoadTestError("fill-ratio must be between 0 and 1")
    if float(resolved["duration"]) <= 0.0:
        raise LoadTestError("duration must be > 0")
    return resolved


def _uuid(run_id: str, kind: str, index: str | int) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"cintafactory:{run_id}:{kind}:{index}")


def _stable_number(seed: int, *parts: object) -> int:
    raw = ":".join([str(seed), *(str(part) for part in parts)])
    return int(hashlib.sha256(raw.encode("utf-8")).hexdigest(), 16)


def _selected(seed: int, fill_ratio: float, *parts: object) -> bool:
    value = _stable_number(seed, *parts) % 1_000_000
    return value < int(fill_ratio * 1_000_000)


def _payload_value(data_type: str, slot: int, prefix: str) -> object:
    if data_type == DATPartEntryType.BOOLEAN:
        return bool(slot % 2)
    if data_type == DATPartEntryType.INTEGER:
        return -9_000_000_000 - slot
    if data_type == DATPartEntryType.DECIMAL:
        return f"-{9_000_000 + slot}.25"
    if data_type == DATPartEntryType.DATE:
        return (date(2040, 1, 1) + timedelta(days=slot)).isoformat()
    if data_type == DATPartEntryType.JSON:
        return {"load_test": prefix.rstrip("-"), "slot": slot}
    if data_type == DATPartEntryType.REPEATER:
        return [{"load_test": prefix.rstrip("-"), "slot": slot}]
    if data_type == DATPartEntryType.URL:
        return f"https://load.invalid/{prefix}{slot}"
    if data_type == DATPartEntryType.LONG_TEXT:
        return f"{prefix}long-text-{slot} " * 8
    return f"{prefix}text-{slot}"


def _payload_hash(value: object) -> str:
    normalized = DATPartPayload._normalize_for_hash(value)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _blueprint_shape() -> tuple[int, int, int, tuple[str, ...]]:
    section_count = len(SECTION_BLUEPRINTS)
    sub_section_count = sum(len(section.get("parts", ())) for section in SECTION_BLUEPRINTS)
    part_count = sum(
        len(sub_section.get("entries", ()))
        for section in SECTION_BLUEPRINTS
        for sub_section in section.get("parts", ())
    )
    data_types = tuple(
        sorted(
            {
                str(entry["type"])
                for section in SECTION_BLUEPRINTS
                for sub_section in section.get("parts", ())
                for entry in sub_section.get("entries", ())
            }
        )
    )
    return section_count, sub_section_count, part_count, data_types


def _create_payload_pool(config: SeedConfig) -> tuple[dict[tuple[str, int], uuid.UUID], list[uuid.UUID]]:
    _, _, _, data_types = _blueprint_shape()
    candidates: dict[str, tuple[uuid.UUID, object]] = {}
    lookup_hash: dict[tuple[str, int], str] = {}
    for data_type in data_types:
        for slot in range(PAYLOAD_VALUES_PER_TYPE):
            value = DATPartPayload._coerce_json_value(_payload_value(data_type, slot, config.prefix))
            payload_hash = _payload_hash(value)
            lookup_hash[(data_type, slot)] = payload_hash
            candidates.setdefault(
                payload_hash,
                (_uuid(config.run_id, "payload", payload_hash), value),
            )

    existing_hashes = set(
        DATPartPayload.objects.filter(hash__in=candidates).values_list("hash", flat=True)
    )
    created_hashes = set(candidates) - existing_hashes
    DATPartPayload.objects.bulk_create(
        [
            DATPartPayload(id=payload_id, hash=payload_hash, data=value)
            for payload_hash, (payload_id, value) in candidates.items()
            if payload_hash in created_hashes
        ],
        batch_size=config.batch_size,
    )
    hash_to_id = dict(
        DATPartPayload.objects.filter(hash__in=candidates).values_list("hash", "id")
    )
    pool = {key: hash_to_id[payload_hash] for key, payload_hash in lookup_hash.items()}
    created_ids = [hash_to_id[payload_hash] for payload_hash in sorted(created_hashes)]
    return pool, created_ids


def _load_run_exists(prefix: str) -> bool:
    User = get_user_model()
    return any(
        (
            DAT.objects.filter(reference__startswith=prefix).exists(),
            Application.objects.filter(code__startswith=prefix).exists(),
            User.objects.filter(username__startswith=prefix).exists(),
        )
    )


def seed_database(config: SeedConfig, *, progress: ProgressCallback | None = None) -> dict[str, object]:
    validate_run_id(config.run_id)
    if config.users < 1 or config.applications < 1 or config.dats < 1:
        raise LoadTestError("users, applications and dats must be >= 1")
    if not 0.0 <= config.fill_ratio <= 1.0:
        raise LoadTestError("fill-ratio must be between 0 and 1")
    if config.batch_size < 1:
        raise LoadTestError("batch-size must be >= 1")
    if _load_run_exists(config.prefix):
        raise LoadTestError(f"run already exists: {config.run_id}")

    started = time.perf_counter()
    User = get_user_model()
    direction_count = min(REFERENCE_DIRECTION_COUNT, config.users, config.applications)
    direction_count = max(direction_count, 1)

    technical_directions = [
        TechnicalDirection(
            id=_uuid(config.run_id, "technical-direction", index),
            name=f"{config.prefix}technical-{index}",
            slug=f"{config.prefix}technical-{index}",
        )
        for index in range(direction_count)
    ]
    business_directions = [
        BusinessDirection(
            id=_uuid(config.run_id, "business-direction", index),
            name=f"{config.prefix}business-{index}",
            slug=f"{config.prefix}business-{index}",
        )
        for index in range(direction_count)
    ]
    roles = [
        Role(
            id=_uuid(config.run_id, "role", f"{direction_index}-{role_index}"),
            name=f"{config.prefix}role-{direction_index}-{role_index}",
            slug=f"{config.prefix}role-{direction_index}-{role_index}",
            technical_direction=technical_directions[direction_index],
        )
        for direction_index in range(direction_count)
        for role_index in range(ROLES_PER_DIRECTION)
    ]

    with transaction.atomic():
        TechnicalDirection.objects.bulk_create(technical_directions, batch_size=config.batch_size)
        BusinessDirection.objects.bulk_create(business_directions, batch_size=config.batch_size)
        Role.objects.bulk_create(roles, batch_size=config.batch_size)

        bootstrap_user = User(
            id=_uuid(config.run_id, "user", 0),
            username=f"{config.prefix}user-00000000",
            email=f"{config.prefix}user-0@load.invalid",
            first_name="Load",
            last_name="User 0",
            password=make_password(None),
            role=roles[0],
            is_active=True,
        )
        User.objects.bulk_create([bootstrap_user])

        groups = [
            BusinessGroup(
                id=_uuid(config.run_id, "group", index),
                name=f"{config.prefix}group-{index}",
                direction=technical_directions[index],
                responsible=bootstrap_user,
                is_default=True,
                business_direction=business_directions[index],
            )
            for index in range(direction_count)
        ]
        BusinessGroup.objects.bulk_create(groups, batch_size=config.batch_size)
        User.objects.filter(pk=bootstrap_user.pk).update(business_group=groups[0])
        bootstrap_user.business_group = groups[0]

        users = [bootstrap_user]
        for index in range(1, config.users):
            direction_index = index % direction_count
            user = User(
                id=_uuid(config.run_id, "user", index),
                username=f"{config.prefix}user-{index:08d}",
                email=f"{config.prefix}user-{index}@load.invalid",
                first_name="Load",
                last_name=f"User {index}",
                password=make_password(None),
                role=roles[direction_index * ROLES_PER_DIRECTION + (index % ROLES_PER_DIRECTION)],
                business_group=groups[direction_index],
                is_active=True,
            )
            users.append(user)
        User.objects.bulk_create(users[1:], batch_size=config.batch_size)

        applications = [
            Application(
                id=_uuid(config.run_id, "application", index),
                code=f"{config.prefix}app-{index:08d}",
                name=f"{config.prefix}Application {index}",
                description=f"Synthetic application for load-test run {config.run_id}",
                business_direction=business_directions[index % direction_count],
            )
            for index in range(config.applications)
        ]
        Application.objects.bulk_create(applications, batch_size=config.batch_size)

        payload_pool, created_payload_ids = _create_payload_pool(config)
        manifest = {
            "run_id": config.run_id,
            "created_payload_ids": [str(item) for item in created_payload_ids],
        }
        applications[0].description = MANIFEST_PREFIX + json.dumps(manifest, sort_keys=True)
        Application.objects.filter(pk=applications[0].pk).update(
            description=applications[0].description
        )

    if progress:
        progress(
            f"reference data: users={config.users} applications={config.applications} "
            f"payloads={len(payload_pool)}"
        )

    section_role_through = DATSection.allowed_roles.through
    sub_section_role_through = DATSubSection.allowed_roles.through
    section_source = DATSection._meta.get_field("allowed_roles").m2m_field_name()
    section_target = DATSection._meta.get_field("allowed_roles").m2m_reverse_field_name()
    sub_source = DATSubSection._meta.get_field("allowed_roles").m2m_field_name()
    sub_target = DATSubSection._meta.get_field("allowed_roles").m2m_reverse_field_name()
    statuses = tuple(DATStatus.values)
    total_entries = 0
    total_batches = math.ceil(config.dats / config.batch_size)

    for batch_number, start in enumerate(range(0, config.dats, config.batch_size), start=1):
        stop = min(start + config.batch_size, config.dats)
        dats: list[DAT] = []
        histories: list[DATHistory] = []
        participants: list[DATParticipant] = []
        admins: list[DATAdmin] = []
        metadata_rows: list[DATSectionMetadata] = []
        sections: list[DATSection] = []
        sub_sections: list[DATSubSection] = []
        parts: list[DATPart] = []
        entries: list[DATPartEntry] = []
        responsibles: list[DATSectionResponsible] = []
        section_participants: list[DATSectionParticipant] = []
        section_roles: list[object] = []
        sub_section_roles: list[object] = []

        for dat_index in range(start, stop):
            application = applications[dat_index % len(applications)]
            owner = users[dat_index % len(users)]
            dat = DAT(
                id=_uuid(config.run_id, "dat", dat_index),
                reference=f"{config.prefix}dat-{dat_index:08d}",
                title=f"Load test {config.run_id} DAT {dat_index}",
                description=f"Synthetic DAT generated with seed {config.seed}",
                application=application,
                business_direction_id=application.business_direction_id,
                owner=owner,
                status=statuses[_stable_number(config.seed, "status", dat_index) % len(statuses)],
            )
            dats.append(dat)
            details: dict[str, object] = {
                "load_test": {"run_id": config.run_id, "seed": config.seed}
            }
            if dat_index == 0:
                load_marker = details["load_test"]
                if isinstance(load_marker, dict):
                    load_marker["created_payload_ids"] = [str(item) for item in created_payload_ids]
            histories.append(
                DATHistory(
                    id=_uuid(config.run_id, "history", dat_index),
                    dat=dat,
                    action=DATHistoryAction.CREATED,
                    performed_by=owner,
                    performed_by_display=owner.username,
                    details=details,
                )
            )
            participants.append(
                DATParticipant(
                    id=_uuid(config.run_id, "participant", dat_index),
                    dat=dat,
                    role_id=owner.role_id,
                    user=owner,
                    participant_type=DATParticipantType.RESPONSABLE,
                )
            )
            admins.append(
                DATAdmin(
                    id=_uuid(config.run_id, "admin", dat_index),
                    dat=dat,
                    user=owner,
                )
            )

            for section_index, section_definition in enumerate(SECTION_BLUEPRINTS):
                section_key = f"{dat_index}:{section_index}"
                metadata = DATSectionMetadata(
                    id=_uuid(config.run_id, "section-metadata", section_key),
                    title=section_definition["title"],
                    slug=section_definition["slug"],
                    description=section_definition.get("description", ""),
                )
                section = DATSection(
                    id=_uuid(config.run_id, "section", section_key),
                    dat=dat,
                    metadata=metadata,
                    order=section_index,
                )
                metadata_rows.append(metadata)
                sections.append(section)
                role = owner.role
                section_roles.append(
                    section_role_through(
                        **{
                            f"{section_source}_id": section.id,
                            f"{section_target}_id": role.id,
                        }
                    )
                )
                responsibles.append(
                    DATSectionResponsible(
                        id=_uuid(config.run_id, "section-responsible", section_key),
                        dat=dat,
                        section=section,
                        user=owner,
                    )
                )
                section_participants.append(
                    DATSectionParticipant(
                        id=_uuid(config.run_id, "section-participant", section_key),
                        dat=dat,
                        section=section,
                        user=owner,
                    )
                )

                for sub_index, sub_definition in enumerate(section_definition.get("parts", ())):
                    sub_key = f"{section_key}:{sub_index}"
                    sub_section = DATSubSection(
                        id=_uuid(config.run_id, "sub-section", sub_key),
                        section=section,
                        title=sub_definition["title"],
                        slug=sub_definition["slug"],
                        order=sub_index,
                        description=sub_definition.get("description", ""),
                    )
                    sub_sections.append(sub_section)
                    sub_section_roles.append(
                        sub_section_role_through(
                            **{
                                f"{sub_source}_id": sub_section.id,
                                f"{sub_target}_id": role.id,
                            }
                        )
                    )

                    for part_index, part_definition in enumerate(sub_definition.get("entries", ())):
                        part_key = f"{sub_key}:{part_index}"
                        data_type = str(part_definition["type"])
                        part = DATPart(
                            id=_uuid(config.run_id, "part", part_key),
                            sub_section=sub_section,
                            key=part_definition["key"],
                            label=part_definition["label"],
                            data_type=data_type,
                            required=part_definition.get("required", False),
                            order=part_index,
                            config=part_definition.get("config"),
                        )
                        parts.append(part)
                        if _selected(config.seed, config.fill_ratio, "entry", part_key):
                            slot = _stable_number(config.seed, "payload", part_key) % PAYLOAD_VALUES_PER_TYPE
                            entries.append(
                                DATPartEntry(
                                    id=_uuid(config.run_id, "entry", part_key),
                                    part=part,
                                    payload_id=payload_pool[(data_type, slot)],
                                )
                            )

        with transaction.atomic():
            DAT.objects.bulk_create(dats, batch_size=config.batch_size)
            DATHistory.objects.bulk_create(histories, batch_size=config.batch_size)
            DATParticipant.objects.bulk_create(participants, batch_size=config.batch_size)
            DATAdmin.objects.bulk_create(admins, batch_size=config.batch_size)
            DATSectionMetadata.objects.bulk_create(metadata_rows, batch_size=config.batch_size)
            DATSection.objects.bulk_create(sections, batch_size=config.batch_size)
            section_role_through.objects.bulk_create(section_roles, batch_size=config.batch_size)
            DATSectionResponsible.objects.bulk_create(responsibles, batch_size=config.batch_size)
            DATSectionParticipant.objects.bulk_create(section_participants, batch_size=config.batch_size)
            DATSubSection.objects.bulk_create(sub_sections, batch_size=config.batch_size)
            sub_section_role_through.objects.bulk_create(sub_section_roles, batch_size=config.batch_size)
            DATPart.objects.bulk_create(parts, batch_size=config.batch_size)
            DATPartEntry.objects.bulk_create(entries, batch_size=config.batch_size)
        total_entries += len(entries)
        if progress:
            progress(f"DAT batch {batch_number}/{total_batches}: {stop}/{config.dats}")

    expected = {
        "users": config.users,
        "applications": config.applications,
        "dats": config.dats,
        "entries": total_entries,
    }
    integrity = validate_seeded_run(config.run_id, expected=expected)
    elapsed = time.perf_counter() - started
    return {
        "action": "seed",
        "run_id": config.run_id,
        "prefix": config.prefix,
        "seed": config.seed,
        "elapsed_seconds": round(elapsed, 3),
        "throughput_dats_per_second": round(config.dats / elapsed, 3) if elapsed else 0.0,
        "counts": integrity["counts"],
        "integrity": integrity,
        "passed": bool(integrity["passed"]),
    }


def _value_matches_type(data_type: str, value: object) -> bool:
    if data_type == DATPartEntryType.BOOLEAN:
        return isinstance(value, bool)
    if data_type == DATPartEntryType.INTEGER:
        return isinstance(value, int) and not isinstance(value, bool)
    if data_type == DATPartEntryType.DECIMAL:
        try:
            Decimal(str(value))
            return True
        except (InvalidOperation, TypeError, ValueError):
            return False
    if data_type == DATPartEntryType.DATE:
        try:
            date.fromisoformat(str(value))
            return True
        except ValueError:
            return False
    if data_type == DATPartEntryType.JSON:
        return isinstance(value, (dict, list))
    if data_type == DATPartEntryType.REPEATER:
        return isinstance(value, list)
    return isinstance(value, str)


def validate_seeded_run(run_id: str, *, expected: dict[str, int] | None = None) -> dict[str, object]:
    prefix = run_prefix(run_id)
    section_count, sub_section_count, part_count, _ = _blueprint_shape()
    dats = DAT.objects.filter(reference__startswith=prefix)
    counts = {
        "users": get_user_model().objects.filter(username__startswith=prefix).count(),
        "applications": Application.objects.filter(code__startswith=prefix).count(),
        "dats": dats.count(),
        "sections": DATSection.objects.filter(dat__reference__startswith=prefix).count(),
        "sub_sections": DATSubSection.objects.filter(section__dat__reference__startswith=prefix).count(),
        "parts": DATPart.objects.filter(sub_section__section__dat__reference__startswith=prefix).count(),
        "entries": DATPartEntry.objects.filter(part__sub_section__section__dat__reference__startswith=prefix).count(),
        "participants": DATParticipant.objects.filter(dat__reference__startswith=prefix).count(),
        "admins": DATAdmin.objects.filter(dat__reference__startswith=prefix).count(),
        "history": DATHistory.objects.filter(dat__reference__startswith=prefix).count(),
        "section_responsibles": DATSectionResponsible.objects.filter(dat__reference__startswith=prefix).count(),
        "section_participants": DATSectionParticipant.objects.filter(dat__reference__startswith=prefix).count(),
    }
    expected_counts = dict(expected or {})
    expected_counts.update(
        {
            "sections": counts["dats"] * section_count,
            "sub_sections": counts["dats"] * sub_section_count,
            "parts": counts["dats"] * part_count,
            "participants": counts["dats"],
            "admins": counts["dats"],
            "history": counts["dats"],
            "section_responsibles": counts["dats"] * section_count,
            "section_participants": counts["dats"] * section_count,
        }
    )
    failures = [
        f"{name}: expected {value}, got {counts.get(name)}"
        for name, value in expected_counts.items()
        if counts.get(name) != value
    ]
    broken_directions = dats.exclude(
        business_direction_id=F("application__business_direction_id")
    ).count()
    if broken_directions:
        failures.append(f"{broken_directions} DAT rows have inconsistent business direction")

    sample = list(
        DATPartEntry.objects.filter(part__sub_section__section__dat__reference__startswith=prefix)
        .select_related("part", "payload")
        .order_by("id")[:100]
    )
    invalid_payloads = sum(
        1 for entry in sample if not _value_matches_type(entry.part.data_type, entry.resolved_value)
    )
    if invalid_payloads:
        failures.append(f"{invalid_payloads} sampled payloads do not match field types")
    return {
        "passed": not failures,
        "failures": failures,
        "counts": counts,
        "sampled_payloads": len(sample),
    }


class _MetricsRecorder:
    def __init__(self, *, seed: int = 0) -> None:
        self._lock = threading.Lock()
        self._rng = random.Random(seed)
        self.total = 0
        self.errors = 0
        self.total_ms = 0.0
        self.max_ms = 0.0
        self.samples: list[float] = []
        self.statuses: Counter[int] = Counter()
        self.error_messages: list[str] = []

    def record(self, elapsed_ms: float, *, status: int = 200, error: str | None = None) -> None:
        with self._lock:
            self.total += 1
            self.total_ms += elapsed_ms
            self.max_ms = max(self.max_ms, elapsed_ms)
            self.statuses[status] += 1
            if error is not None:
                self.errors += 1
                if len(self.error_messages) < MAX_REPORTED_ERRORS:
                    self.error_messages.append(error)
            if len(self.samples) < MAX_LATENCY_SAMPLES:
                self.samples.append(elapsed_ms)
            else:
                index = self._rng.randrange(self.total)
                if index < MAX_LATENCY_SAMPLES:
                    self.samples[index] = elapsed_ms

    def summary(self, *, elapsed_seconds: float) -> dict[str, object]:
        error_rate = self.errors / self.total if self.total else 0.0
        return {
            "total_operations": self.total,
            "success_count": self.total - self.errors,
            "error_count": self.errors,
            "error_rate": round(error_rate, 6),
            "throughput_per_second": round(self.total / elapsed_seconds, 3) if elapsed_seconds else 0.0,
            "elapsed_seconds": round(elapsed_seconds, 3),
            "latency_ms": {
                "average": round(self.total_ms / self.total, 3) if self.total else 0.0,
                "p50": round(percentile_ms(self.samples, 50), 3),
                "p95": round(percentile_ms(self.samples, 95), 3),
                "p99": round(percentile_ms(self.samples, 99), 3),
                "max": round(self.max_ms, 3),
                "sample_count": len(self.samples),
            },
            "statuses": {str(key): value for key, value in sorted(self.statuses.items())},
            "errors": self.error_messages,
        }


def evaluate_thresholds(metrics: dict[str, object], thresholds: Thresholds) -> dict[str, object]:
    failures: list[str] = []
    latency = metrics.get("latency_ms", {})
    p95_ms = float(latency.get("p95", 0.0)) if isinstance(latency, dict) else 0.0
    error_rate = float(metrics.get("error_rate", 0.0))
    throughput = float(metrics.get("throughput_per_second", 0.0))
    if thresholds.max_p95_ms is not None and p95_ms > thresholds.max_p95_ms:
        failures.append(f"p95 {p95_ms:.3f}ms > {thresholds.max_p95_ms:.3f}ms")
    if thresholds.max_error_rate is not None and error_rate > thresholds.max_error_rate:
        failures.append(f"error rate {error_rate:.6f} > {thresholds.max_error_rate:.6f}")
    if thresholds.min_throughput is not None and throughput < thresholds.min_throughput:
        failures.append(f"throughput {throughput:.3f}/s < {thresholds.min_throughput:.3f}/s")
    return {
        "passed": not failures,
        "failures": failures,
        "thresholds": asdict(thresholds),
    }


def run_db_load(
    run_id: str,
    *,
    mode: str,
    duration: float,
    concurrency: int,
    read_ratio: float,
    seed: int,
    thresholds: Thresholds | None = None,
) -> dict[str, object]:
    prefix = run_prefix(run_id)
    if mode not in {"read", "write", "mixed"}:
        raise LoadTestError("db mode must be read, write or mixed")
    if duration <= 0 or concurrency < 1:
        raise LoadTestError("duration must be > 0 and concurrency must be >= 1")
    if not 0.0 <= read_ratio <= 1.0:
        raise LoadTestError("read-ratio must be between 0 and 1")
    dat_ids = list(
        DAT.objects.filter(reference__startswith=prefix).order_by("id").values_list("id", flat=True)
    )
    if not dat_ids:
        raise LoadTestError(f"no DAT data found for run: {run_id}")

    recorder = _MetricsRecorder(seed=seed)
    deadline = time.monotonic() + duration
    statuses = tuple(DATStatus.values)

    def worker(worker_index: int) -> None:
        rng = random.Random(_stable_number(seed, "db-worker", worker_index))
        close_old_connections()
        try:
            while time.monotonic() < deadline:
                do_read = mode == "read" or (mode == "mixed" and rng.random() < read_ratio)
                dat_id = dat_ids[rng.randrange(len(dat_ids))]
                started = time.perf_counter()
                try:
                    if do_read:
                        operation = rng.randrange(3)
                        if operation == 0:
                            DAT.objects.filter(
                                reference__startswith=prefix,
                                status=statuses[rng.randrange(len(statuses))],
                            ).count()
                        elif operation == 1:
                            row = (
                                DAT.objects.filter(pk=dat_id, reference__startswith=prefix)
                                .select_related("application", "owner", "business_direction")
                                .values("reference", "status", "application__name", "owner__username")
                                .first()
                            )
                            if row is None:
                                raise LoadTestError("synthetic DAT disappeared during read workload")
                        else:
                            list(
                                DAT.objects.filter(reference__startswith=prefix, title__icontains="Load test")
                                .order_by("-created_at")
                                .values_list("id", flat=True)[:25]
                            )
                    else:
                        updated = DAT.objects.filter(pk=dat_id, reference__startswith=prefix).update(
                            status=statuses[rng.randrange(len(statuses))],
                            updated_at=timezone.now(),
                        )
                        if updated != 1:
                            raise LoadTestError("write escaped or missed synthetic run boundary")
                except Exception as exc:  # workload must continue and aggregate failures
                    recorder.record(
                        (time.perf_counter() - started) * 1000.0,
                        status=599,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                else:
                    recorder.record((time.perf_counter() - started) * 1000.0)
        finally:
            close_old_connections()

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(worker, index) for index in range(concurrency)]
        for future in futures:
            future.result()
    elapsed = time.perf_counter() - started
    metrics = recorder.summary(elapsed_seconds=elapsed)
    evaluation = evaluate_thresholds(metrics, thresholds or Thresholds())
    return {
        "action": "db",
        "run_id": run_id,
        "mode": mode,
        "duration_requested_seconds": duration,
        "concurrency": concurrency,
        "read_ratio": read_ratio,
        "metrics": metrics,
        "evaluation": evaluation,
        "passed": evaluation["passed"],
    }


def _http_request(url: str, *, timeout: float, oauth_token: str | None) -> tuple[float, int, str | None]:
    headers = {"User-Agent": "CintaFactory-load-test/1.0"}
    if oauth_token:
        headers["Authorization"] = f"Bearer {oauth_token}"
    request = Request(url, headers=headers, method="GET")
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200) or 200)
            response.read(1)
        error = None
    except HTTPError as exc:
        status = int(exc.code or 500)
        error = None
    except URLError as exc:
        status = 599
        error = f"URLError: {exc.reason}"
    except Exception as exc:
        status = 599
        error = f"{type(exc).__name__}: {exc}"
    return (time.perf_counter() - started) * 1000.0, status, error


def run_http_load(
    *,
    base_url: str,
    paths: Sequence[str],
    scenario: str,
    concurrency: int,
    timeout: float,
    total_requests: int | None = None,
    duration: float | None = None,
    oauth_token: str | None = None,
    thresholds: Thresholds | None = None,
    error_status_min: int = 400,
) -> dict[str, object]:
    base_url = validate_url(base_url)
    if not paths:
        raise LoadTestError("at least one HTTP path is required")
    if concurrency < 1 or timeout <= 0:
        raise LoadTestError("concurrency must be >= 1 and timeout must be > 0")
    if (total_requests is None) == (duration is None):
        raise LoadTestError("provide exactly one of requests or duration")
    if total_requests is not None and total_requests < 1:
        raise LoadTestError("requests must be >= 1")
    if duration is not None and duration <= 0:
        raise LoadTestError("duration must be > 0")
    urls = [urljoin(f"{base_url}/", str(path).lstrip("/")) for path in paths]
    recorder = _MetricsRecorder()
    counter_lock = threading.Lock()
    next_index = 0
    deadline = time.monotonic() + duration if duration is not None else None

    def claim() -> int | None:
        nonlocal next_index
        with counter_lock:
            if total_requests is not None and next_index >= total_requests:
                return None
            if deadline is not None and time.monotonic() >= deadline:
                return None
            current = next_index
            next_index += 1
            return current

    def worker() -> None:
        while True:
            index = claim()
            if index is None:
                return
            elapsed_ms, status, request_error = _http_request(
                urls[index % len(urls)], timeout=timeout, oauth_token=oauth_token
            )
            is_error = request_error is not None or status >= error_status_min
            error = request_error or (f"HTTP {status}" if is_error else None)
            recorder.record(elapsed_ms, status=status, error=error)

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(worker) for _ in range(concurrency)]
        for future in futures:
            future.result()
    elapsed = time.perf_counter() - started
    metrics = recorder.summary(elapsed_seconds=elapsed)
    configured = evaluate_thresholds(metrics, thresholds or Thresholds())
    slo_summary = LoadSummary(
        scenario=scenario,
        total_requests=int(metrics["total_operations"]),
        error_count=int(metrics["error_count"]),
        p95_ms=float(metrics["latency_ms"]["p95"]),  # type: ignore[index]
        p99_ms=float(metrics["latency_ms"]["p99"]),  # type: ignore[index]
    )
    scenario_slo = evaluate_slo(slo_summary)
    passed = bool(configured["passed"] and scenario_slo["passed"])
    return {
        "action": "http",
        "scenario": scenario,
        "base_url": base_url,
        "paths": list(paths),
        "oauth": bool(oauth_token),
        "concurrency": concurrency,
        "timeout_seconds": timeout,
        "metrics": metrics,
        "evaluation": configured,
        "scenario_slo": scenario_slo,
        "passed": passed,
    }


def load_run_counts(run_id: str) -> dict[str, int]:
    prefix = run_prefix(run_id)
    return {
        "dats": DAT.objects.filter(reference__startswith=prefix).count(),
        "applications": Application.objects.filter(code__startswith=prefix).count(),
        "users": get_user_model().objects.filter(username__startswith=prefix).count(),
        "groups": BusinessGroup.objects.filter(name__startswith=prefix).count(),
        "roles": Role.objects.filter(slug__startswith=prefix).count(),
        "technical_directions": TechnicalDirection.objects.filter(slug__startswith=prefix).count(),
        "business_directions": BusinessDirection.objects.filter(slug__startswith=prefix).count(),
    }


def _raw_delete(queryset) -> int:
    """
    Delete already-isolated leaf rows without making Django traverse every
    third-party reverse relation. PostgreSQL foreign keys still reject any
    unsafe deletion if an explicit dependency was missed.
    """
    return int(queryset._raw_delete(queryset.db))


@contextmanager
def _without_dat_delete_logging():
    from dat.signals import log_dat_delete

    disconnected = post_delete.disconnect(log_dat_delete, sender=DAT)
    try:
        yield
    finally:
        if disconnected:
            post_delete.connect(log_dat_delete, sender=DAT)


def cleanup_run(
    run_id: str,
    *,
    batch_size: int = 250,
    dry_run: bool = False,
    progress: ProgressCallback | None = None,
) -> dict[str, object]:
    prefix = run_prefix(run_id)
    if batch_size < 1:
        raise LoadTestError("batch-size must be >= 1")
    before = load_run_counts(run_id)
    if dry_run:
        return {
            "action": "cleanup",
            "run_id": run_id,
            "dry_run": True,
            "counts": before,
            "passed": True,
        }

    metadata_ids = list(
        DATSection.objects.filter(dat__reference__startswith=prefix).values_list("metadata_id", flat=True)
    )
    created_payload_ids: set[uuid.UUID] = set()
    for description in Application.objects.filter(code__startswith=prefix).values_list(
        "description", flat=True
    ):
        if not str(description).startswith(MANIFEST_PREFIX):
            continue
        try:
            manifest = json.loads(str(description)[len(MANIFEST_PREFIX) :])
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(manifest, dict) or manifest.get("run_id") != run_id:
            continue
        for raw_id in manifest.get("created_payload_ids", ()):
            try:
                created_payload_ids.add(uuid.UUID(str(raw_id)))
            except (TypeError, ValueError):
                continue
    for details in DATHistory.objects.filter(dat__reference__startswith=prefix).values_list("details", flat=True):
        if not isinstance(details, dict):
            continue
        marker = details.get("load_test")
        if not isinstance(marker, dict) or marker.get("run_id") != run_id:
            continue
        for raw_id in marker.get("created_payload_ids", ()):
            try:
                created_payload_ids.add(uuid.UUID(str(raw_id)))
            except (TypeError, ValueError):
                continue

    deleted_total = 0
    with _without_dat_delete_logging():
        while True:
            ids = list(
                DAT.objects.filter(reference__startswith=prefix).values_list("id", flat=True)[:batch_size]
            )
            if not ids:
                break
            deleted, _ = DAT.objects.filter(id__in=ids).delete()
            deleted_total += deleted
            if progress:
                progress(f"cleanup DAT batch: {len(ids)}")

    if metadata_ids:
        _raw_delete(DATSectionMetadata.objects.filter(id__in=metadata_ids, section__isnull=True))
    _raw_delete(Application.objects.filter(code__startswith=prefix))
    User = get_user_model()
    User.objects.filter(username__startswith=prefix).update(business_group=None)
    _raw_delete(BusinessGroup.objects.filter(name__startswith=prefix))
    _raw_delete(User.objects.filter(username__startswith=prefix))
    _raw_delete(Role.objects.filter(slug__startswith=prefix))
    _raw_delete(TechnicalDirection.objects.filter(slug__startswith=prefix))
    _raw_delete(BusinessDirection.objects.filter(slug__startswith=prefix))
    if created_payload_ids:
        _raw_delete(DATPartPayload.objects.filter(id__in=created_payload_ids, entries__isnull=True))

    after = load_run_counts(run_id)
    remaining = sum(after.values())
    return {
        "action": "cleanup",
        "run_id": run_id,
        "dry_run": False,
        "counts_before": before,
        "counts_after": after,
        "deleted_objects": deleted_total,
        "passed": remaining == 0,
        "failures": [] if remaining == 0 else [f"{remaining} tagged top-level objects remain"],
    }


def public_config(config: SeedConfig) -> dict[str, object]:
    return asdict(config)


__all__ = [
    "LOAD_PROFILES",
    "LoadProfile",
    "LoadTestError",
    "SeedConfig",
    "Thresholds",
    "cleanup_run",
    "ensure_load_test_allowed",
    "evaluate_thresholds",
    "load_run_counts",
    "public_config",
    "resolve_profile",
    "run_db_load",
    "run_http_load",
    "run_prefix",
    "seed_database",
    "validate_run_id",
    "validate_seeded_run",
    "validate_url",
]
