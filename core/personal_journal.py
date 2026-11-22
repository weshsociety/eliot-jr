from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class PersonalJournalError(ValueError):
    """Erreur de validation du journal personnel Eliot-Jr."""


def _utc_now(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)

    if value.tzinfo is None:
        raise PersonalJournalError(
            "Un timestamp sans fuseau horaire est interdit."
        )

    return (
        value.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise PersonalJournalError(
            "La structure doit être sérialisable en JSON canonique."
        ) from error


def _payload_hash(
    payload: dict[str, Any],
    hash_field: str,
) -> str:
    material = copy.deepcopy(payload)
    material.pop(hash_field, None)

    return hashlib.sha256(
        _canonical_bytes(material)
    ).hexdigest()


def _require_string(
    value: Any,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PersonalJournalError(
            f"{field_name} doit être une chaîne non vide."
        )

    return value


def _require_unique_string_list(
    value: Any,
    field_name: str,
) -> list[str]:
    if not isinstance(value, list):
        raise PersonalJournalError(
            f"{field_name} doit être une liste."
        )

    seen: set[str] = set()

    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise PersonalJournalError(
                f"{field_name} ne peut contenir que "
                "des chaînes non vides."
            )

        if item in seen:
            raise PersonalJournalError(
                f"{field_name} contient un doublon."
            )

        seen.add(item)

    return value


def build_personal_journal_entry(
    *,
    content: str,
    linked_refs: list[str] | None = None,
    reinterprets_entry_ids: list[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Construit une entrée libre.

    Aucun champ émotion, leçon, conclusion ou diagnostic
    n'est exigé.
    """
    timestamp = _utc_now(now)

    entry: dict[str, Any] = {
        "schema_version": 1,
        "identity": "Eliot-Jr",
        "kind": "personal_journal_entry",
        "created_at_utc": timestamp,
        "content": _require_string(
            content,
            "content",
        ),
        "linked_refs": copy.deepcopy(
            _require_unique_string_list(
                linked_refs or [],
                "linked_refs",
            )
        ),
        "reinterprets_entry_ids": copy.deepcopy(
            _require_unique_string_list(
                reinterprets_entry_ids or [],
                "reinterprets_entry_ids",
            )
        ),
        "free_form": True,
        "emotion_field_required": False,
        "lesson_field_required": False,
        "conclusion_required": False,
        "subjective_state_claimed_by_system": False,
        "external_action_performed": False,
    }

    entry["entry_sha256"] = _payload_hash(
        entry,
        "entry_sha256",
    )

    entry["entry_id"] = (
        "personal_journal_"
        + timestamp.replace(":", "").replace("-", "")
        + "_"
        + entry["entry_sha256"][:12]
    )

    entry["entry_sha256"] = _payload_hash(
        entry,
        "entry_sha256",
    )

    return validate_personal_journal_entry(entry)


def validate_personal_journal_entry(
    entry: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise PersonalJournalError(
            "entry doit être un objet."
        )

    if entry.get("schema_version") != 1:
        raise PersonalJournalError(
            "Version d'entrée de journal non supportée."
        )

    if entry.get("identity") != "Eliot-Jr":
        raise PersonalJournalError(
            "Identité du journal invalide."
        )

    if entry.get("kind") != "personal_journal_entry":
        raise PersonalJournalError(
            "Type d'entrée de journal invalide."
        )

    _require_string(
        entry.get("entry_id"),
        "entry_id",
    )
    _require_string(
        entry.get("created_at_utc"),
        "created_at_utc",
    )
    _require_string(
        entry.get("content"),
        "content",
    )

    _require_unique_string_list(
        entry.get("linked_refs"),
        "linked_refs",
    )
    _require_unique_string_list(
        entry.get("reinterprets_entry_ids"),
        "reinterprets_entry_ids",
    )

    if entry.get("free_form") is not True:
        raise PersonalJournalError(
            "Une entrée personnelle doit rester libre."
        )

    for field_name in (
        "emotion_field_required",
        "lesson_field_required",
        "conclusion_required",
        "subjective_state_claimed_by_system",
        "external_action_performed",
    ):
        if entry.get(field_name) is not False:
            raise PersonalJournalError(
                f"{field_name} doit rester False."
            )

    expected_hash = _payload_hash(
        entry,
        "entry_sha256",
    )

    if entry.get("entry_sha256") != expected_hash:
        raise PersonalJournalError(
            "Hash de l'entrée personnelle invalide."
        )

    return entry


def build_empty_personal_journal(
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    timestamp = _utc_now(now)

    journal: dict[str, Any] = {
        "schema_version": 1,
        "identity": "Eliot-Jr",
        "kind": "personal_journal",
        "created_at_utc": timestamp,
        "updated_at_utc": timestamp,
        "entry_count": 0,
        "entries": [],
        "append_only": True,
        "writing_required": False,
        "missing_entry_is_error": False,
        "automatic_prompting_enabled": False,
        "external_action_performed": False,
    }

    journal["journal_sha256"] = _payload_hash(
        journal,
        "journal_sha256",
    )

    return validate_personal_journal(journal)


def validate_personal_journal(
    journal: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(journal, dict):
        raise PersonalJournalError(
            "journal doit être un objet."
        )

    if journal.get("schema_version") != 1:
        raise PersonalJournalError(
            "Version du journal non supportée."
        )

    if journal.get("identity") != "Eliot-Jr":
        raise PersonalJournalError(
            "Identité du journal invalide."
        )

    if journal.get("kind") != "personal_journal":
        raise PersonalJournalError(
            "Type de journal invalide."
        )

    if journal.get("append_only") is not True:
        raise PersonalJournalError(
            "Le journal personnel doit rester append-only."
        )

    if journal.get("writing_required") is not False:
        raise PersonalJournalError(
            "L'écriture ne peut pas être obligatoire."
        )

    if journal.get("missing_entry_is_error") is not False:
        raise PersonalJournalError(
            "L'absence d'entrée ne peut pas être une erreur."
        )

    if journal.get("automatic_prompting_enabled") is not False:
        raise PersonalJournalError(
            "Le journal ne peut pas imposer "
            "une sollicitation automatique."
        )

    if journal.get("external_action_performed") is not False:
        raise PersonalJournalError(
            "Le journal ne peut pas effectuer "
            "une action extérieure."
        )

    entries = journal.get("entries")

    if not isinstance(entries, list):
        raise PersonalJournalError(
            "entries doit être une liste."
        )

    if journal.get("entry_count") != len(entries):
        raise PersonalJournalError(
            "entry_count est incohérent."
        )

    seen_ids: set[str] = set()
    seen_hashes: set[str] = set()

    for entry in entries:
        validate_personal_journal_entry(entry)

        entry_id = entry["entry_id"]
        entry_hash = entry["entry_sha256"]

        if entry_id in seen_ids:
            raise PersonalJournalError(
                "Une entrée ne peut apparaître deux fois."
            )

        if entry_hash in seen_hashes:
            raise PersonalJournalError(
                "Une entrée identique ne peut être dupliquée."
            )

        seen_ids.add(entry_id)
        seen_hashes.add(entry_hash)

    expected_hash = _payload_hash(
        journal,
        "journal_sha256",
    )

    if journal.get("journal_sha256") != expected_hash:
        raise PersonalJournalError(
            "Hash du journal personnel invalide."
        )

    return journal


def load_personal_journal(
    path: Path | str,
) -> dict[str, Any]:
    journal_path = Path(path)

    if not journal_path.exists():
        raise PersonalJournalError(
            f"Journal personnel absent : {journal_path}"
        )

    try:
        payload = json.loads(
            journal_path.read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError) as error:
        raise PersonalJournalError(
            "Journal personnel illisible ou corrompu."
        ) from error

    return validate_personal_journal(payload)


def _load_or_empty(
    path: Path,
    *,
    now: datetime | None,
) -> dict[str, Any]:
    if path.exists():
        return load_personal_journal(path)

    return build_empty_personal_journal(now=now)


def preview_personal_journal_append(
    path: Path | str,
    entry: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Prépare l'ajout sans écrire sur disque.
    """
    journal_path = Path(path)

    candidate_entry = copy.deepcopy(
        validate_personal_journal_entry(entry)
    )

    journal = _load_or_empty(
        journal_path,
        now=now,
    )

    for existing in journal["entries"]:
        if (
            existing["entry_sha256"]
            == candidate_entry["entry_sha256"]
        ):
            return {
                "schema_version": 1,
                "identity": "Eliot-Jr",
                "mode": "preview",
                "status": "already_recorded",
                "entry_id": existing["entry_id"],
                "journal_path": str(journal_path),
                "journal_mutation_applied": False,
                "external_action_performed": False,
                "candidate_journal": copy.deepcopy(
                    journal
                ),
            }

    candidate_journal = copy.deepcopy(journal)
    candidate_journal["entries"].append(
        candidate_entry
    )
    candidate_journal["entry_count"] = len(
        candidate_journal["entries"]
    )
    candidate_journal["updated_at_utc"] = _utc_now(now)
    candidate_journal["journal_sha256"] = _payload_hash(
        candidate_journal,
        "journal_sha256",
    )

    validate_personal_journal(
        candidate_journal
    )

    return {
        "schema_version": 1,
        "identity": "Eliot-Jr",
        "mode": "preview",
        "status": "append_ready",
        "entry_id": candidate_entry["entry_id"],
        "journal_path": str(journal_path),
        "journal_mutation_applied": False,
        "external_action_performed": False,
        "candidate_journal": candidate_journal,
    }


def _write_json_atomic(
    path: Path,
    payload: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )

    try:
        with os.fdopen(
            descriptor,
            "w",
            encoding="utf-8",
        ) as handle:
            json.dump(
                payload,
                handle,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(
            temporary_name,
            path,
        )

    except Exception:
        try:
            os.unlink(temporary_name)
        except OSError:
            pass
        raise


def commit_personal_journal_append(
    path: Path | str,
    entry: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Ajoute explicitement une entrée.

    Cette fonction n'est jamais appelée automatiquement
    par ce module.
    """
    journal_path = Path(path)

    preview = preview_personal_journal_append(
        journal_path,
        entry,
        now=now,
    )

    if preview["status"] == "already_recorded":
        result = copy.deepcopy(preview)
        result["mode"] = "commit"
        return result

    _write_json_atomic(
        journal_path,
        preview["candidate_journal"],
    )

    persisted = load_personal_journal(
        journal_path
    )

    result = copy.deepcopy(preview)
    result["mode"] = "commit"
    result["status"] = "committed"
    result["journal_mutation_applied"] = True
    result["candidate_journal"] = persisted

    return result
