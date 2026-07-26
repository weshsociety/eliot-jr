from __future__ import annotations

import fcntl
import json
import os
import re
import tempfile
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any


REGISTRY_VERSION = 1


def _canonical_json(data: Any) -> str:
    return json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _hash_value(data: Any) -> str:
    return sha256(_canonical_json(data).encode("utf-8")).hexdigest()


def _normalise(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(
        character
        for character in text
        if not unicodedata.combining(character)
    )
    text = text.lower().strip()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _declared_time(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None

    value = (
        data.get("timestamp")
        or data.get("created_at")
        or data.get("date")
    )

    if value in (None, ""):
        return None

    return str(value)


def _display_name(data: Any) -> str | None:
    if not isinstance(data, dict):
        return None

    value = (
        data.get("name")
        or data.get("title")
        or data.get("label")
    )

    if value in (None, ""):
        return None

    return str(value)


def _identity(record: dict[str, Any]) -> dict[str, Any]:
    data = record.get("data")
    file_name = str(record.get("file", ""))
    section = str(record.get("section", ""))

    if isinstance(data, dict):
        explicit_id = data.get("id")

        if explicit_id not in (None, ""):
            descriptor = _display_name(data) or ""

            return {
                "kind": "explicit",
                "file": file_name,
                "section": section,
                "explicit_id": str(explicit_id),
                "descriptor": _normalise(descriptor),
                "revision_tracking": "stable_composite_anchor",
            }

        declared_time = _declared_time(data)

        if declared_time is not None:
            return {
                "kind": "timestamp",
                "file": file_name,
                "section": section,
                "declared_time": declared_time,
                "revision_tracking": "stable_timestamp_anchor",
            }

        book_id = data.get("book_id")

        if book_id not in (None, ""):
            return {
                "kind": "book",
                "file": file_name,
                "section": section,
                "book_id": str(book_id),
                "revision_tracking": "stable_book_anchor",
            }

    return {
        "kind": "content_only",
        "file": file_name,
        "section": section,
        "content_anchor": _hash_value(data),
        "revision_tracking": "content_addressed_limited",
    }


def _memory_id(identity: dict[str, Any]) -> str:
    digest = _hash_value(identity)
    return f"memory_{digest[:24]}"


def build_fragment_snapshot(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    grouped: dict[str, dict[str, Any]] = {}
    identity_hashes: dict[str, set[str]] = defaultdict(set)

    for record in records:
        data = record.get("data")
        identity = _identity(record)
        memory_id = _memory_id(identity)
        content_hash = _hash_value(data)

        identity_hashes[memory_id].add(content_hash)

        if memory_id not in grouped:
            grouped[memory_id] = {
                "memory_id": memory_id,
                "identity": identity,
                "display_name": _display_name(data),
                "source_declared_at": _declared_time(data),
                "content_hash": content_hash,
                "copy_count": 0,
            }

        grouped[memory_id]["copy_count"] += 1

    collisions = {
        memory_id: sorted(hashes)
        for memory_id, hashes in identity_hashes.items()
        if len(hashes) > 1
    }

    kinds = Counter(
        memory["identity"]["kind"]
        for memory in grouped.values()
    )

    duplicate_groups = sum(
        1
        for memory in grouped.values()
        if memory["copy_count"] > 1
    )

    return {
        "records_count": len(records),
        "unique_memories": len(grouped),
        "duplicate_records": len(records) - len(grouped),
        "duplicate_groups": duplicate_groups,
        "identity_kinds": dict(sorted(kinds.items())),
        "collisions": collisions,
        "memories": grouped,
    }


def _read_registry(
    registry_path: Path,
) -> tuple[dict[str, Any], list[str]]:
    if not registry_path.is_file():
        return {}, []

    try:
        data = json.loads(
            registry_path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [f"Registre des fragments illisible : {exc}"]

    if not isinstance(data, dict):
        return {}, [
            "Le registre des fragments n’est pas un objet JSON."
        ]

    return data, []


def _write_atomic(
    path: Path,
    data: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=path.parent,
    )

    try:
        with os.fdopen(
            descriptor,
            "w",
            encoding="utf-8",
        ) as temporary:
            json.dump(
                data,
                temporary,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())

        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)

    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def synchronise_fragment_history(
    records: list[dict[str, Any]],
    registry_path: Path,
    now: datetime | None = None,
    commit: bool = True,
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    current_time = now or datetime.now(timezone.utc)

    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)

    current_time = current_time.astimezone(timezone.utc)
    timestamp = current_time.isoformat()

    snapshot = build_fragment_snapshot(records)

    if snapshot["collisions"]:
        raise ValueError(
            "Des identités temporelles regroupent plusieurs "
            "contenus distincts."
        )

    registry_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = registry_path.with_suffix(
        registry_path.suffix + ".lock"
    )

    warnings: list[str] = []

    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)

        existing, read_warnings = _read_registry(registry_path)
        warnings.extend(read_warnings)

        previous_memories = existing.get("memories", {})

        if not isinstance(previous_memories, dict):
            previous_memories = {}
            warnings.append(
                "La collection memories était invalide ; "
                "elle a été reconstruite."
            )

        updated_memories = dict(previous_memories)

        new_count = 0
        unchanged_count = 0
        changed_count = 0

        current_ids = set(snapshot["memories"])

        for memory_id, current in snapshot["memories"].items():
            previous = previous_memories.get(memory_id)

            if not isinstance(previous, dict):
                new_count += 1

                updated_memories[memory_id] = {
                    "memory_id": memory_id,
                    "identity": current["identity"],
                    "display_name": current["display_name"],
                    "source_declared_at": current[
                        "source_declared_at"
                    ],
                    "first_seen_at_utc": timestamp,
                    "last_observed_at_utc": timestamp,
                    "observation_count": 1,
                    "active": True,
                    "current_content_hash": current[
                        "content_hash"
                    ],
                    "current_copy_count": current[
                        "copy_count"
                    ],
                    "maximum_copy_count_seen": current[
                        "copy_count"
                    ],
                    "versions": {
                        current["content_hash"]: {
                            "first_seen_at_utc": timestamp,
                            "last_seen_at_utc": timestamp,
                            "observation_count": 1,
                        }
                    },
                }
                continue

            previous_hash = previous.get(
                "current_content_hash"
            )
            current_hash = current["content_hash"]

            versions = previous.get("versions", {})

            if not isinstance(versions, dict):
                versions = {}

            version = versions.get(current_hash)

            if not isinstance(version, dict):
                version = {
                    "first_seen_at_utc": timestamp,
                    "last_seen_at_utc": timestamp,
                    "observation_count": 1,
                }
            else:
                version = dict(version)
                version["last_seen_at_utc"] = timestamp
                version["observation_count"] = (
                    int(version.get("observation_count", 0)) + 1
                )

            versions = dict(versions)
            versions[current_hash] = version

            updated = dict(previous)
            updated.update({
                "identity": current["identity"],
                "display_name": current["display_name"],
                "source_declared_at": current[
                    "source_declared_at"
                ],
                "last_observed_at_utc": timestamp,
                "observation_count": (
                    int(previous.get("observation_count", 0)) + 1
                ),
                "active": True,
                "current_content_hash": current_hash,
                "current_copy_count": current["copy_count"],
                "maximum_copy_count_seen": max(
                    int(
                        previous.get(
                            "maximum_copy_count_seen",
                            0,
                        )
                    ),
                    current["copy_count"],
                ),
                "versions": versions,
            })

            if previous_hash != current_hash:
                changed_count += 1
                updated["last_changed_at_utc"] = timestamp
                updated["previous_content_hash"] = previous_hash
            else:
                unchanged_count += 1

            updated_memories[memory_id] = updated

        missing_count = 0

        for memory_id, previous in previous_memories.items():
            if memory_id in current_ids:
                continue

            if not isinstance(previous, dict):
                continue

            missing_count += 1
            updated = dict(previous)
            updated["active"] = False
            updated.setdefault("first_missing_at_utc", timestamp)
            updated["last_missing_at_utc"] = timestamp
            updated_memories[memory_id] = updated

        registry = {
            "version": REGISTRY_VERSION,
            "created_at_utc": existing.get(
                "created_at_utc",
                timestamp,
            ),
            "updated_at_utc": timestamp,
            "memories": updated_memories,
        }

        report = {
            "records_observed": snapshot["records_count"],
            "unique_memories_observed": snapshot[
                "unique_memories"
            ],
            "duplicate_records_observed": snapshot[
                "duplicate_records"
            ],
            "duplicate_groups_observed": snapshot[
                "duplicate_groups"
            ],
            "identity_kinds": snapshot["identity_kinds"],
            "new_memories": new_count,
            "unchanged_memories": unchanged_count,
            "changed_memories": changed_count,
            "missing_memories": missing_count,
            "registry_total_after_sync": len(
                updated_memories
            ),
            "committed": commit,
        }

        if commit:
            _write_atomic(registry_path, registry)

        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    return registry, report, warnings



def attach_fragment_metadata(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Attache à chaque occurrence son souvenir stable et sa version,
    sans modifier les données originales.
    """
    annotated: list[dict[str, Any]] = []

    for record in records:
        enriched = dict(record)
        identity = _identity(record)

        enriched["memory_id"] = _memory_id(identity)
        enriched["content_hash"] = _hash_value(
            record.get("data")
        )
        annotated.append(enriched)

    return annotated


def record_fragment_usage(
    registry_path: Path,
    usages: list[dict[str, str]],
    interaction_number: int,
    used_at_utc: str,
    commit: bool = True,
) -> tuple[dict[str, Any], list[str]]:
    """
    Inscrit uniquement les souvenirs réellement utilisés dans une réponse.

    Charger ou indexer un fragment ne constitue pas une relecture.
    """
    unique_usages: dict[str, dict[str, str]] = {}

    for usage in usages:
        memory_id = str(usage.get("memory_id", "")).strip()

        if not memory_id:
            continue

        unique_usages[memory_id] = {
            "memory_id": memory_id,
            "content_hash": str(
                usage.get("content_hash", "")
            ).strip(),
        }

    report: dict[str, Any] = {
        "interaction_number": interaction_number,
        "requested_memories": len(unique_usages),
        "used_memories": 0,
        "missing_memories": 0,
        "committed": commit,
    }

    if not unique_usages:
        return report, []

    registry_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = registry_path.with_suffix(
        registry_path.suffix + ".lock"
    )

    warnings: list[str] = []

    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)

        registry, read_warnings = _read_registry(
            registry_path
        )
        warnings.extend(read_warnings)

        memories = registry.get("memories", {})

        if not isinstance(memories, dict):
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            return report, warnings + [
                "La collection memories du registre est invalide."
            ]

        updated_memories = dict(memories)

        for memory_id, usage in unique_usages.items():
            memory = memories.get(memory_id)

            if not isinstance(memory, dict):
                report["missing_memories"] += 1
                warnings.append(
                    f"Souvenir absent du registre : {memory_id}"
                )
                continue

            updated = dict(memory)
            history = updated.get("usage_history", [])

            if not isinstance(history, list):
                history = []

            event = {
                "interaction_number": int(
                    interaction_number
                ),
                "used_at_utc": used_at_utc,
                "content_hash": usage["content_hash"],
            }

            # Une même réponse ne doit compter un souvenir qu’une fois.
            already_recorded = any(
                isinstance(previous, dict)
                and previous.get("interaction_number")
                == interaction_number
                for previous in history
            )

            if already_recorded:
                continue

            history = list(history)
            history.append(event)

            updated.setdefault(
                "first_used_at_utc",
                used_at_utc,
            )
            updated["last_used_at_utc"] = used_at_utc
            updated["last_used_interaction"] = int(
                interaction_number
            )
            updated["usage_count"] = (
                int(updated.get("usage_count", 0)) + 1
            )
            updated["usage_history"] = history

            updated_memories[memory_id] = updated
            report["used_memories"] += 1

        if commit and report["used_memories"]:
            registry = dict(registry)
            registry["updated_at_utc"] = used_at_utc
            registry["memories"] = updated_memories
            _write_atomic(registry_path, registry)

        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    return report, warnings
