from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any


class MemoryAccessibilityError(ValueError):
    """Erreur de validation de l'accessibilité mémoire."""


def _utc_now(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)

    if value.tzinfo is None:
        raise MemoryAccessibilityError(
            "Un timestamp sans fuseau horaire est interdit."
        )

    return (
        value.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _parse_utc(value: str, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise MemoryAccessibilityError(
            f"{field_name} doit être une chaîne non vide."
        )

    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError as error:
        raise MemoryAccessibilityError(
            f"{field_name} n'est pas un timestamp ISO valide."
        ) from error

    if parsed.tzinfo is None:
        raise MemoryAccessibilityError(
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
        raise MemoryAccessibilityError(
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
        raise MemoryAccessibilityError(
            f"{field_name} doit être une chaîne non vide."
        )

    return value


def _require_non_negative_int(
    value: Any,
    field_name: str,
) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value < 0
    ):
        raise MemoryAccessibilityError(
            f"{field_name} doit être un entier positif ou nul."
        )

    return value


def _require_string_list(
    value: Any,
    field_name: str,
) -> list[str]:
    if not isinstance(value, list):
        raise MemoryAccessibilityError(
            f"{field_name} doit être une liste."
        )

    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise MemoryAccessibilityError(
                f"{field_name} ne peut contenir que "
                "des chaînes non vides."
            )

    return value


def build_memory_accessibility_snapshot(
    *,
    memory_ref: str,
    archive_ref: str,
    encounter_count: int,
    reactivation_count: int,
    currently_reactivated: bool,
    last_encountered_at_utc: str | None = None,
    last_reactivated_at_utc: str | None = None,
    active_context_refs: list[str] | None = None,
    reactivation_trigger_refs: list[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Observe l'accessibilité fonctionnelle d'une mémoire.

    Aucun oubli, importance, émotion ou état subjectif
    n'est déduit.
    """
    observed_at = _utc_now(now)
    observed_dt = _parse_utc(
        observed_at,
        "observed_at_utc",
    )

    if not isinstance(currently_reactivated, bool):
        raise MemoryAccessibilityError(
            "currently_reactivated doit être booléen."
        )

    encounters = _require_non_negative_int(
        encounter_count,
        "encounter_count",
    )
    reactivations = _require_non_negative_int(
        reactivation_count,
        "reactivation_count",
    )

    if reactivations > encounters:
        raise MemoryAccessibilityError(
            "reactivation_count ne peut pas dépasser "
            "encounter_count."
        )

    encountered_dt = None

    if last_encountered_at_utc is not None:
        encountered_dt = _parse_utc(
            last_encountered_at_utc,
            "last_encountered_at_utc",
        )

        if encountered_dt > observed_dt:
            raise MemoryAccessibilityError(
                "La dernière rencontre ne peut pas "
                "être postérieure à l'observation."
            )

    reactivated_dt = None

    if last_reactivated_at_utc is not None:
        reactivated_dt = _parse_utc(
            last_reactivated_at_utc,
            "last_reactivated_at_utc",
        )

        if reactivated_dt > observed_dt:
            raise MemoryAccessibilityError(
                "La dernière réactivation ne peut pas "
                "être postérieure à l'observation."
            )

    if encounters == 0 and encountered_dt is not None:
        raise MemoryAccessibilityError(
            "Une mémoire jamais rencontrée ne peut pas "
            "avoir de date de dernière rencontre."
        )

    if reactivations == 0 and reactivated_dt is not None:
        raise MemoryAccessibilityError(
            "Une mémoire jamais réactivée ne peut pas "
            "avoir de date de dernière réactivation."
        )

    if currently_reactivated and reactivations == 0:
        raise MemoryAccessibilityError(
            "Une mémoire actuellement réactivée doit "
            "avoir au moins une réactivation."
        )

    elapsed_since_encounter = None

    if encountered_dt is not None:
        elapsed_since_encounter = int(
            (
                observed_dt - encountered_dt
            ).total_seconds()
        )

    elapsed_since_reactivation = None

    if reactivated_dt is not None:
        elapsed_since_reactivation = int(
            (
                observed_dt - reactivated_dt
            ).total_seconds()
        )

    snapshot: dict[str, Any] = {
        "schema_version": 1,
        "identity": "Eliot-Jr",
        "kind": "memory_accessibility_snapshot",
        "observed_at_utc": observed_at,
        "memory_ref": _require_string(
            memory_ref,
            "memory_ref",
        ),
        "archive_ref": _require_string(
            archive_ref,
            "archive_ref",
        ),
        "archive_retained": True,
        "encounter_count": encounters,
        "reactivation_count": reactivations,
        "currently_reactivated": currently_reactivated,
        "last_encountered_at_utc": (
            last_encountered_at_utc
        ),
        "last_reactivated_at_utc": (
            last_reactivated_at_utc
        ),
        "elapsed_since_last_encounter_seconds": (
            elapsed_since_encounter
        ),
        "elapsed_since_last_reactivation_seconds": (
            elapsed_since_reactivation
        ),
        "active_context_refs": copy.deepcopy(
            _require_string_list(
                active_context_refs or [],
                "active_context_refs",
            )
        ),
        "reactivation_trigger_refs": copy.deepcopy(
            _require_string_list(
                reactivation_trigger_refs or [],
                "reactivation_trigger_refs",
            )
        ),
        "importance_claimed": False,
        "salience_score_assigned": False,
        "forgetting_applied": False,
        "archive_mutation_applied": False,
        "subjective_state_claimed": False,
        "external_action_performed": False,
    }

    snapshot["snapshot_sha256"] = _payload_hash(
        snapshot,
        "snapshot_sha256",
    )

    return validate_memory_accessibility_snapshot(
        snapshot
    )


def validate_memory_accessibility_snapshot(
    snapshot: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        raise MemoryAccessibilityError(
            "snapshot doit être un objet."
        )

    if snapshot.get("schema_version") != 1:
        raise MemoryAccessibilityError(
            "Version du snapshot mémoire non supportée."
        )

    if snapshot.get("identity") != "Eliot-Jr":
        raise MemoryAccessibilityError(
            "Identité du snapshot mémoire invalide."
        )

    if (
        snapshot.get("kind")
        != "memory_accessibility_snapshot"
    ):
        raise MemoryAccessibilityError(
            "Type de snapshot mémoire invalide."
        )

    observed_dt = _parse_utc(
        snapshot.get("observed_at_utc"),
        "observed_at_utc",
    )

    _require_string(
        snapshot.get("memory_ref"),
        "memory_ref",
    )
    _require_string(
        snapshot.get("archive_ref"),
        "archive_ref",
    )

    if snapshot.get("archive_retained") is not True:
        raise MemoryAccessibilityError(
            "La mémoire historique doit rester conservée."
        )

    encounters = _require_non_negative_int(
        snapshot.get("encounter_count"),
        "encounter_count",
    )
    reactivations = _require_non_negative_int(
        snapshot.get("reactivation_count"),
        "reactivation_count",
    )

    if reactivations > encounters:
        raise MemoryAccessibilityError(
            "Nombre de réactivations incohérent."
        )

    currently_reactivated = snapshot.get(
        "currently_reactivated"
    )

    if not isinstance(currently_reactivated, bool):
        raise MemoryAccessibilityError(
            "currently_reactivated doit être booléen."
        )

    encountered = snapshot.get(
        "last_encountered_at_utc"
    )
    reactivated = snapshot.get(
        "last_reactivated_at_utc"
    )

    encountered_dt = None

    if encountered is not None:
        encountered_dt = _parse_utc(
            encountered,
            "last_encountered_at_utc",
        )

        if encountered_dt > observed_dt:
            raise MemoryAccessibilityError(
                "La dernière rencontre est dans le futur."
            )

        expected = int(
            (
                observed_dt - encountered_dt
            ).total_seconds()
        )

        if (
            snapshot.get(
                "elapsed_since_last_encounter_seconds"
            )
            != expected
        ):
            raise MemoryAccessibilityError(
                "Durée depuis la dernière rencontre invalide."
            )

    elif (
        snapshot.get(
            "elapsed_since_last_encounter_seconds"
        )
        is not None
    ):
        raise MemoryAccessibilityError(
            "Une durée de rencontre existe sans date."
        )

    reactivated_dt = None

    if reactivated is not None:
        reactivated_dt = _parse_utc(
            reactivated,
            "last_reactivated_at_utc",
        )

        if reactivated_dt > observed_dt:
            raise MemoryAccessibilityError(
                "La dernière réactivation est dans le futur."
            )

        expected = int(
            (
                observed_dt - reactivated_dt
            ).total_seconds()
        )

        if (
            snapshot.get(
                "elapsed_since_last_reactivation_seconds"
            )
            != expected
        ):
            raise MemoryAccessibilityError(
                "Durée depuis la dernière réactivation invalide."
            )

    elif (
        snapshot.get(
            "elapsed_since_last_reactivation_seconds"
        )
        is not None
    ):
        raise MemoryAccessibilityError(
            "Une durée de réactivation existe sans date."
        )

    if encounters == 0 and encountered_dt is not None:
        raise MemoryAccessibilityError(
            "Date de rencontre incompatible avec encounter_count."
        )

    if reactivations == 0 and reactivated_dt is not None:
        raise MemoryAccessibilityError(
            "Date de réactivation incompatible "
            "avec reactivation_count."
        )

    if currently_reactivated and reactivations == 0:
        raise MemoryAccessibilityError(
            "Réactivation actuelle sans historique "
            "de réactivation."
        )

    _require_string_list(
        snapshot.get("active_context_refs"),
        "active_context_refs",
    )
    _require_string_list(
        snapshot.get("reactivation_trigger_refs"),
        "reactivation_trigger_refs",
    )

    for field_name in (
        "importance_claimed",
        "salience_score_assigned",
        "forgetting_applied",
        "archive_mutation_applied",
        "subjective_state_claimed",
        "external_action_performed",
    ):
        if snapshot.get(field_name) is not False:
            raise MemoryAccessibilityError(
                f"{field_name} doit rester False."
            )

    expected_hash = _payload_hash(
        snapshot,
        "snapshot_sha256",
    )

    if snapshot.get("snapshot_sha256") != expected_hash:
        raise MemoryAccessibilityError(
            "Hash du snapshot mémoire invalide."
        )

    return snapshot
