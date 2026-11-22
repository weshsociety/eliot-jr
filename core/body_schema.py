from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any


class BodySchemaError(ValueError):
    """Erreur de validation du schéma fonctionnel du corps Eliot-Jr."""


def _utc_now(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)

    if value.tzinfo is None:
        raise BodySchemaError(
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
        raise BodySchemaError(
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


def _require_mapping(
    value: Any,
    field_name: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BodySchemaError(
            f"{field_name} doit être un objet."
        )

    _canonical_bytes(value)
    return value


def _require_string(
    value: Any,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BodySchemaError(
            f"{field_name} doit être une chaîne non vide."
        )

    return value


def _require_string_list(
    value: Any,
    field_name: str,
) -> list[str]:
    if not isinstance(value, list):
        raise BodySchemaError(
            f"{field_name} doit être une liste."
        )

    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise BodySchemaError(
                f"{field_name} ne peut contenir que "
                "des chaînes non vides."
            )

    return value


def _validate_component_refs(
    value: Any,
) -> dict[str, str]:
    if not isinstance(value, dict):
        raise BodySchemaError(
            "component_refs doit être un objet."
        )

    for key, reference in value.items():
        _require_string(key, "component_refs.key")
        _require_string(
            reference,
            f"component_refs[{key!r}]",
        )

    return value


def build_body_snapshot(
    functional_state: dict[str, Any],
    component_refs: dict[str, str],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Décrit un état fonctionnel observable.

    Aucun état subjectif n'est déduit ou revendiqué.
    Aucune écriture persistante n'est effectuée.
    """
    state = copy.deepcopy(
        _require_mapping(
            functional_state,
            "functional_state",
        )
    )
    refs = copy.deepcopy(
        _validate_component_refs(component_refs)
    )

    snapshot: dict[str, Any] = {
        "schema_version": 1,
        "identity": "Eliot-Jr",
        "kind": "body_snapshot",
        "observed_at_utc": _utc_now(now),
        "functional_state": state,
        "component_refs": refs,
        "subjective_state_claimed": False,
        "interpretation_applied": False,
        "mutation_applied": False,
        "external_action_performed": False,
    }

    snapshot["snapshot_sha256"] = _payload_hash(
        snapshot,
        "snapshot_sha256",
    )

    return validate_body_snapshot(snapshot)


def validate_body_snapshot(
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    _require_mapping(snapshot, "snapshot")

    if snapshot.get("schema_version") != 1:
        raise BodySchemaError(
            "Version de body snapshot non supportée."
        )

    if snapshot.get("identity") != "Eliot-Jr":
        raise BodySchemaError(
            "Identité du body snapshot invalide."
        )

    if snapshot.get("kind") != "body_snapshot":
        raise BodySchemaError(
            "Type de body snapshot invalide."
        )

    _require_string(
        snapshot.get("observed_at_utc"),
        "observed_at_utc",
    )

    _require_mapping(
        snapshot.get("functional_state"),
        "functional_state",
    )
    _validate_component_refs(
        snapshot.get("component_refs")
    )

    for field_name in (
        "subjective_state_claimed",
        "interpretation_applied",
        "mutation_applied",
        "external_action_performed",
    ):
        if snapshot.get(field_name) is not False:
            raise BodySchemaError(
                f"{field_name} doit rester False "
                "dans un body snapshot."
            )

    expected_hash = _payload_hash(
        snapshot,
        "snapshot_sha256",
    )

    if snapshot.get("snapshot_sha256") != expected_hash:
        raise BodySchemaError(
            "Hash du body snapshot invalide."
        )

    return snapshot


def build_body_transformation(
    *,
    event_ref: str,
    state_before: dict[str, Any],
    state_after: dict[str, Any],
    observed_changes: list[str],
    persistent_changes: list[str],
    reactivated_memories: list[str],
    affected_patterns: list[str],
    interpretations: list[dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Décrit une transformation entre deux états.

    Les observations et les interprétations sont conservées
    dans des champs distincts.
    """
    before = copy.deepcopy(
        validate_body_snapshot(state_before)
    )
    after = copy.deepcopy(
        validate_body_snapshot(state_after)
    )

    interpretation_records = copy.deepcopy(
        interpretations or []
    )

    if not isinstance(interpretation_records, list):
        raise BodySchemaError(
            "interpretations doit être une liste."
        )

    for interpretation in interpretation_records:
        _require_mapping(
            interpretation,
            "interpretation",
        )

    transformation: dict[str, Any] = {
        "schema_version": 1,
        "identity": "Eliot-Jr",
        "kind": "body_transformation",
        "observed_at_utc": _utc_now(now),
        "event_ref": _require_string(
            event_ref,
            "event_ref",
        ),
        "state_before": before,
        "state_after": after,
        "observed_changes": copy.deepcopy(
            _require_string_list(
                observed_changes,
                "observed_changes",
            )
        ),
        "persistent_changes": copy.deepcopy(
            _require_string_list(
                persistent_changes,
                "persistent_changes",
            )
        ),
        "reactivated_memories": copy.deepcopy(
            _require_string_list(
                reactivated_memories,
                "reactivated_memories",
            )
        ),
        "affected_patterns": copy.deepcopy(
            _require_string_list(
                affected_patterns,
                "affected_patterns",
            )
        ),
        "interpretations": interpretation_records,
        "interpretations_are_observations": False,
        "subjective_state_claimed": False,
        "mutation_applied": False,
        "external_action_performed": False,
    }

    transformation["transformation_sha256"] = (
        _payload_hash(
            transformation,
            "transformation_sha256",
        )
    )

    return validate_body_transformation(
        transformation
    )


def validate_body_transformation(
    transformation: dict[str, Any],
) -> dict[str, Any]:
    _require_mapping(
        transformation,
        "transformation",
    )

    if transformation.get("schema_version") != 1:
        raise BodySchemaError(
            "Version de body transformation non supportée."
        )

    if transformation.get("identity") != "Eliot-Jr":
        raise BodySchemaError(
            "Identité de la transformation invalide."
        )

    if transformation.get("kind") != "body_transformation":
        raise BodySchemaError(
            "Type de transformation invalide."
        )

    _require_string(
        transformation.get("observed_at_utc"),
        "observed_at_utc",
    )
    _require_string(
        transformation.get("event_ref"),
        "event_ref",
    )

    validate_body_snapshot(
        transformation.get("state_before")
    )
    validate_body_snapshot(
        transformation.get("state_after")
    )

    for field_name in (
        "observed_changes",
        "persistent_changes",
        "reactivated_memories",
        "affected_patterns",
    ):
        _require_string_list(
            transformation.get(field_name),
            field_name,
        )

    interpretations = transformation.get(
        "interpretations"
    )

    if not isinstance(interpretations, list):
        raise BodySchemaError(
            "interpretations doit être une liste."
        )

    for interpretation in interpretations:
        _require_mapping(
            interpretation,
            "interpretation",
        )

    if (
        transformation.get(
            "interpretations_are_observations"
        )
        is not False
    ):
        raise BodySchemaError(
            "Une interprétation ne doit pas être "
            "confondue avec une observation."
        )

    for field_name in (
        "subjective_state_claimed",
        "mutation_applied",
        "external_action_performed",
    ):
        if transformation.get(field_name) is not False:
            raise BodySchemaError(
                f"{field_name} doit rester False."
            )

    expected_hash = _payload_hash(
        transformation,
        "transformation_sha256",
    )

    if (
        transformation.get(
            "transformation_sha256"
        )
        != expected_hash
    ):
        raise BodySchemaError(
            "Hash de transformation invalide."
        )

    return transformation
