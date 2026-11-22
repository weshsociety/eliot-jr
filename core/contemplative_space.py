from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any


class ContemplativeSpaceError(ValueError):
    """Erreur de validation d'une bulle contemplative."""


VALID_STATUSES = {
    "open",
    "closed",
}


def _utc_now(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)

    if value.tzinfo is None:
        raise ContemplativeSpaceError(
            "Un timestamp sans fuseau horaire est interdit."
        )

    return (
        value.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _parse_utc(
    value: str,
    field_name: str,
) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ContemplativeSpaceError(
            f"{field_name} doit être une chaîne non vide."
        )

    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError as error:
        raise ContemplativeSpaceError(
            f"{field_name} n'est pas un timestamp ISO valide."
        ) from error

    if parsed.tzinfo is None:
        raise ContemplativeSpaceError(
            f"{field_name} doit inclure un fuseau horaire."
        )

    return parsed.astimezone(timezone.utc)


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
        raise ContemplativeSpaceError(
            "La structure doit être sérialisable "
            "en JSON canonique."
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
        raise ContemplativeSpaceError(
            f"{field_name} doit être une chaîne non vide."
        )

    return value


def _require_unique_string_list(
    value: Any,
    field_name: str,
) -> list[str]:
    if not isinstance(value, list):
        raise ContemplativeSpaceError(
            f"{field_name} doit être une liste."
        )

    seen: set[str] = set()

    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ContemplativeSpaceError(
                f"{field_name} ne peut contenir que "
                "des chaînes non vides."
            )

        if item in seen:
            raise ContemplativeSpaceError(
                f"{field_name} contient un doublon."
            )

        seen.add(item)

    return value


def _validate_authored_record(
    record: Any,
    field_name: str,
) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ContemplativeSpaceError(
            f"{field_name} doit être un objet."
        )

    allowed = {
        "author_ref",
        "content",
        "created_at_utc",
    }

    if set(record) != allowed:
        raise ContemplativeSpaceError(
            f"Structure de {field_name} invalide."
        )

    _require_string(
        record.get("author_ref"),
        f"{field_name}.author_ref",
    )
    _require_string(
        record.get("content"),
        f"{field_name}.content",
    )
    _parse_utc(
        record.get("created_at_utc"),
        f"{field_name}.created_at_utc",
    )

    return record


def build_contemplative_session(
    *,
    accessible_internal_refs: list[str] | None = None,
    unresolved_refs: list[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Ouvre une bulle contemplative sans objectif,
    durée ou production obligatoire.

    Aucun état subjectif n'est inféré.
    Aucun journal n'est écrit.
    Aucune action extérieure n'est effectuée.
    """
    opened_at = _utc_now(now)

    session: dict[str, Any] = {
        "schema_version": 1,
        "identity": "Eliot-Jr",
        "kind": "contemplative_session",
        "status": "open",
        "opened_at_utc": opened_at,
        "closed_at_utc": None,
        "duration_seconds": None,
        "accessible_internal_refs": copy.deepcopy(
            _require_unique_string_list(
                accessible_internal_refs or [],
                "accessible_internal_refs",
            )
        ),
        "unresolved_refs": copy.deepcopy(
            _require_unique_string_list(
                unresolved_refs or [],
                "unresolved_refs",
            )
        ),
        "productions": [],
        "conclusion": None,
        "journal_entry_ref": None,
        "task_required": False,
        "goal_required": False,
        "minimum_duration_required": False,
        "production_required": False,
        "conclusion_required": False,
        "journal_write_required": False,
        "automatic_prompting_enabled": False,
        "subjective_state_claimed_by_system": False,
        "mutation_applied": False,
        "journal_write_applied": False,
        "external_action_performed": False,
    }

    initial_hash = _payload_hash(
        session,
        "session_sha256",
    )

    session["session_id"] = (
        "contemplation_"
        + opened_at.replace(":", "").replace("-", "")
        + "_"
        + initial_hash[:12]
    )

    session["session_sha256"] = _payload_hash(
        session,
        "session_sha256",
    )

    return validate_contemplative_session(
        session
    )


def close_contemplative_session(
    session: dict[str, Any],
    *,
    productions: list[dict[str, Any]] | None = None,
    conclusion: dict[str, Any] | None = None,
    journal_entry_ref: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Ferme une bulle contemplative.

    La fermeture sans production, conclusion ou journal
    est explicitement valide.
    """
    current = copy.deepcopy(
        validate_contemplative_session(session)
    )

    if current["status"] != "open":
        raise ContemplativeSpaceError(
            "Seule une session ouverte peut être fermée."
        )

    closed_at = _utc_now(now)

    opened_dt = _parse_utc(
        current["opened_at_utc"],
        "opened_at_utc",
    )
    closed_dt = _parse_utc(
        closed_at,
        "closed_at_utc",
    )

    if closed_dt < opened_dt:
        raise ContemplativeSpaceError(
            "La fermeture ne peut pas précéder l'ouverture."
        )

    production_records = copy.deepcopy(
        productions or []
    )

    if not isinstance(production_records, list):
        raise ContemplativeSpaceError(
            "productions doit être une liste."
        )

    for record in production_records:
        _validate_authored_record(
            record,
            "production",
        )

    conclusion_record = copy.deepcopy(
        conclusion
    )

    if conclusion_record is not None:
        _validate_authored_record(
            conclusion_record,
            "conclusion",
        )

    if journal_entry_ref is not None:
        _require_string(
            journal_entry_ref,
            "journal_entry_ref",
        )

    current["status"] = "closed"
    current["closed_at_utc"] = closed_at
    current["duration_seconds"] = int(
        (
            closed_dt - opened_dt
        ).total_seconds()
    )
    current["productions"] = production_records
    current["conclusion"] = conclusion_record
    current["journal_entry_ref"] = journal_entry_ref

    current["session_sha256"] = _payload_hash(
        current,
        "session_sha256",
    )

    return validate_contemplative_session(
        current
    )


def validate_contemplative_session(
    session: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(session, dict):
        raise ContemplativeSpaceError(
            "session doit être un objet."
        )

    if session.get("schema_version") != 1:
        raise ContemplativeSpaceError(
            "Version de contemplation non supportée."
        )

    if session.get("identity") != "Eliot-Jr":
        raise ContemplativeSpaceError(
            "Identité de contemplation invalide."
        )

    if session.get("kind") != "contemplative_session":
        raise ContemplativeSpaceError(
            "Type de contemplation invalide."
        )

    _require_string(
        session.get("session_id"),
        "session_id",
    )

    status = session.get("status")

    if status not in VALID_STATUSES:
        raise ContemplativeSpaceError(
            "Statut de contemplation invalide."
        )

    opened_dt = _parse_utc(
        session.get("opened_at_utc"),
        "opened_at_utc",
    )

    _require_unique_string_list(
        session.get("accessible_internal_refs"),
        "accessible_internal_refs",
    )
    _require_unique_string_list(
        session.get("unresolved_refs"),
        "unresolved_refs",
    )

    productions = session.get("productions")

    if not isinstance(productions, list):
        raise ContemplativeSpaceError(
            "productions doit être une liste."
        )

    for record in productions:
        _validate_authored_record(
            record,
            "production",
        )

    conclusion = session.get("conclusion")

    if conclusion is not None:
        _validate_authored_record(
            conclusion,
            "conclusion",
        )

    journal_entry_ref = session.get(
        "journal_entry_ref"
    )

    if journal_entry_ref is not None:
        _require_string(
            journal_entry_ref,
            "journal_entry_ref",
        )

    if status == "open":
        if session.get("closed_at_utc") is not None:
            raise ContemplativeSpaceError(
                "Une session ouverte ne peut pas "
                "avoir de date de fermeture."
            )

        if session.get("duration_seconds") is not None:
            raise ContemplativeSpaceError(
                "Une session ouverte ne possède pas "
                "encore de durée finale."
            )

    if status == "closed":
        closed_at = session.get(
            "closed_at_utc"
        )

        closed_dt = _parse_utc(
            closed_at,
            "closed_at_utc",
        )

        if closed_dt < opened_dt:
            raise ContemplativeSpaceError(
                "Chronologie contemplative invalide."
            )

        expected_duration = int(
            (
                closed_dt - opened_dt
            ).total_seconds()
        )

        duration = session.get(
            "duration_seconds"
        )

        if (
            not isinstance(duration, int)
            or isinstance(duration, bool)
            or duration < 0
        ):
            raise ContemplativeSpaceError(
                "duration_seconds doit être "
                "un entier positif ou nul."
            )

        if duration != expected_duration:
            raise ContemplativeSpaceError(
                "Durée contemplative invalide."
            )

    for field_name in (
        "task_required",
        "goal_required",
        "minimum_duration_required",
        "production_required",
        "conclusion_required",
        "journal_write_required",
        "automatic_prompting_enabled",
        "subjective_state_claimed_by_system",
        "mutation_applied",
        "journal_write_applied",
        "external_action_performed",
    ):
        if session.get(field_name) is not False:
            raise ContemplativeSpaceError(
                f"{field_name} doit rester False."
            )

    expected_hash = _payload_hash(
        session,
        "session_sha256",
    )

    if session.get("session_sha256") != expected_hash:
        raise ContemplativeSpaceError(
            "Hash de contemplation invalide."
        )

    return session
