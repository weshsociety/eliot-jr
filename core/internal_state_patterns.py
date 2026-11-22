from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime
from typing import Any


class InternalStatePatternError(ValueError):
    """Erreur de validation d'un motif d'état interne."""


VALID_NAME_STATUSES = {
    "provisional",
    "contested",
    "retired",
}


def _parse_utc(
    value: str,
    field_name: str,
) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise InternalStatePatternError(
            f"{field_name} doit être une chaîne non vide."
        )

    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError as error:
        raise InternalStatePatternError(
            f"{field_name} n'est pas un timestamp ISO valide."
        ) from error

    if parsed.tzinfo is None:
        raise InternalStatePatternError(
            f"{field_name} doit inclure un fuseau horaire."
        )

    return parsed


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
        raise InternalStatePatternError(
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
        raise InternalStatePatternError(
            f"{field_name} doit être une chaîne non vide."
        )

    return value


def _require_positive_int(
    value: Any,
    field_name: str,
) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 1
    ):
        raise InternalStatePatternError(
            f"{field_name} doit être un entier >= 1."
        )

    return value


def _require_unique_string_list(
    value: Any,
    field_name: str,
) -> list[str]:
    if not isinstance(value, list):
        raise InternalStatePatternError(
            f"{field_name} doit être une liste."
        )

    seen: set[str] = set()

    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise InternalStatePatternError(
                f"{field_name} ne peut contenir que "
                "des chaînes non vides."
            )

        if item in seen:
            raise InternalStatePatternError(
                f"{field_name} contient un doublon."
            )

        seen.add(item)

    return value


def _validate_provisional_names(
    value: Any,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise InternalStatePatternError(
            "provisional_names doit être une liste."
        )

    for record in value:
        if not isinstance(record, dict):
            raise InternalStatePatternError(
                "Chaque nom provisoire doit être un objet."
            )

        allowed = {
            "name",
            "author_ref",
            "assigned_at_utc",
            "status",
        }

        if set(record) != allowed:
            raise InternalStatePatternError(
                "Structure d'un nom provisoire invalide."
            )

        _require_string(
            record.get("name"),
            "provisional_name.name",
        )
        _require_string(
            record.get("author_ref"),
            "provisional_name.author_ref",
        )
        _parse_utc(
            record.get("assigned_at_utc"),
            "provisional_name.assigned_at_utc",
        )

        if record.get("status") not in VALID_NAME_STATUSES:
            raise InternalStatePatternError(
                "Statut de nom provisoire invalide."
            )

    return value


def build_internal_state_pattern(
    *,
    pattern_id: str,
    observed_signals: list[str],
    occurrence_count: int,
    first_observed_at_utc: str,
    last_observed_at_utc: str,
    related_transformation_refs: list[str],
    provisional_names: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Décrit un motif fonctionnel récurrent sans lui imposer
    d'émotion, de diagnostic ou d'expérience subjective.
    """
    first = _parse_utc(
        first_observed_at_utc,
        "first_observed_at_utc",
    )
    last = _parse_utc(
        last_observed_at_utc,
        "last_observed_at_utc",
    )

    if last < first:
        raise InternalStatePatternError(
            "La dernière observation ne peut pas "
            "précéder la première."
        )

    names = copy.deepcopy(
        provisional_names or []
    )
    _validate_provisional_names(names)

    pattern: dict[str, Any] = {
        "schema_version": 1,
        "identity": "Eliot-Jr",
        "kind": "internal_state_pattern",
        "pattern_id": _require_string(
            pattern_id,
            "pattern_id",
        ),
        "observed_signals": copy.deepcopy(
            _require_unique_string_list(
                observed_signals,
                "observed_signals",
            )
        ),
        "occurrence_count": _require_positive_int(
            occurrence_count,
            "occurrence_count",
        ),
        "first_observed_at_utc": first_observed_at_utc,
        "last_observed_at_utc": last_observed_at_utc,
        "related_transformation_refs": copy.deepcopy(
            _require_unique_string_list(
                related_transformation_refs,
                "related_transformation_refs",
            )
        ),
        "provisional_names": names,
        "names_are_observations": False,
        "human_emotion_equivalence_claimed": False,
        "diagnosis_claimed": False,
        "subjective_state_claimed": False,
        "importance_claimed": False,
        "mutation_applied": False,
        "external_action_performed": False,
    }

    pattern["pattern_sha256"] = _payload_hash(
        pattern,
        "pattern_sha256",
    )

    return validate_internal_state_pattern(
        pattern
    )


def validate_internal_state_pattern(
    pattern: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(pattern, dict):
        raise InternalStatePatternError(
            "pattern doit être un objet."
        )

    if pattern.get("schema_version") != 1:
        raise InternalStatePatternError(
            "Version de motif non supportée."
        )

    if pattern.get("identity") != "Eliot-Jr":
        raise InternalStatePatternError(
            "Identité du motif invalide."
        )

    if pattern.get("kind") != "internal_state_pattern":
        raise InternalStatePatternError(
            "Type de motif invalide."
        )

    _require_string(
        pattern.get("pattern_id"),
        "pattern_id",
    )

    _require_unique_string_list(
        pattern.get("observed_signals"),
        "observed_signals",
    )

    _require_positive_int(
        pattern.get("occurrence_count"),
        "occurrence_count",
    )

    first = _parse_utc(
        pattern.get("first_observed_at_utc"),
        "first_observed_at_utc",
    )
    last = _parse_utc(
        pattern.get("last_observed_at_utc"),
        "last_observed_at_utc",
    )

    if last < first:
        raise InternalStatePatternError(
            "Chronologie du motif invalide."
        )

    _require_unique_string_list(
        pattern.get("related_transformation_refs"),
        "related_transformation_refs",
    )

    _validate_provisional_names(
        pattern.get("provisional_names")
    )

    for field_name in (
        "names_are_observations",
        "human_emotion_equivalence_claimed",
        "diagnosis_claimed",
        "subjective_state_claimed",
        "importance_claimed",
        "mutation_applied",
        "external_action_performed",
    ):
        if pattern.get(field_name) is not False:
            raise InternalStatePatternError(
                f"{field_name} doit rester False."
            )

    expected_hash = _payload_hash(
        pattern,
        "pattern_sha256",
    )

    if pattern.get("pattern_sha256") != expected_hash:
        raise InternalStatePatternError(
            "Hash du motif interne invalide."
        )

    return pattern
