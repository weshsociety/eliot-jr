from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.body_schema import (
    BodySchemaError,
    validate_body_transformation,
)


class BodyHistoryError(ValueError):
    """Erreur de validation de l'histoire fonctionnelle du corps."""


def _utc_now(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)

    if value.tzinfo is None:
        raise BodyHistoryError(
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
        raise BodyHistoryError(
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
        raise BodyHistoryError(
            f"{field_name} doit être un objet."
        )

    return value


def _require_string(
    value: Any,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BodyHistoryError(
            f"{field_name} doit être une chaîne non vide."
        )

    return value


def build_empty_body_history(
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    timestamp = _utc_now(now)

    history: dict[str, Any] = {
        "schema_version": 1,
        "identity": "Eliot-Jr",
        "kind": "body_history",
        "created_at_utc": timestamp,
        "updated_at_utc": timestamp,
        "entry_count": 0,
        "entries": [],
        "append_only": True,
        "subjective_state_claimed": False,
        "external_action_performed": False,
    }

    history["registry_sha256"] = _payload_hash(
        history,
        "registry_sha256",
    )

    return validate_body_history(history)


def validate_body_history(
    history: dict[str, Any],
) -> dict[str, Any]:
    _require_mapping(history, "history")

    if history.get("schema_version") != 1:
        raise BodyHistoryError(
            "Version de body history non supportée."
        )

    if history.get("identity") != "Eliot-Jr":
        raise BodyHistoryError(
            "Identité du body history invalide."
        )

    if history.get("kind") != "body_history":
        raise BodyHistoryError(
            "Type de body history invalide."
        )

    _require_string(
        history.get("created_at_utc"),
        "created_at_utc",
    )
    _require_string(
        history.get("updated_at_utc"),
        "updated_at_utc",
    )

    if history.get("append_only") is not True:
        raise BodyHistoryError(
            "Le registre doit rester append-only."
        )

    if history.get("subjective_state_claimed") is not False:
        raise BodyHistoryError(
            "Le registre ne peut revendiquer "
            "un état subjectif."
        )

    if history.get("external_action_performed") is not False:
        raise BodyHistoryError(
            "Le registre ne peut revendiquer "
            "une action extérieure."
        )

    entries = history.get("entries")

    if not isinstance(entries, list):
        raise BodyHistoryError(
            "entries doit être une liste."
        )

    if history.get("entry_count") != len(entries):
        raise BodyHistoryError(
            "entry_count ne correspond pas au contenu."
        )

    previous_entry_hash: str | None = None
    previous_state_after_hash: str | None = None
    seen_transformations: set[str] = set()

    for expected_sequence, entry in enumerate(
        entries,
        start=1,
    ):
        _require_mapping(entry, "entry")

        if entry.get("sequence") != expected_sequence:
            raise BodyHistoryError(
                "Séquence append-only invalide."
            )

        _require_string(
            entry.get("entry_id"),
            "entry_id",
        )
        _require_string(
            entry.get("recorded_at_utc"),
            "recorded_at_utc",
        )

        if (
            entry.get("previous_entry_sha256")
            != previous_entry_hash
        ):
            raise BodyHistoryError(
                "Chaînage cryptographique invalide."
            )

        transformation = entry.get("transformation")

        try:
            validate_body_transformation(
                transformation
            )
        except BodySchemaError as error:
            raise BodyHistoryError(
                "Transformation corporelle invalide."
            ) from error

        transformation_hash = transformation[
            "transformation_sha256"
        ]

        if transformation_hash in seen_transformations:
            raise BodyHistoryError(
                "Une transformation ne peut être "
                "inscrite deux fois."
            )

        seen_transformations.add(
            transformation_hash
        )

        current_before_hash = transformation[
            "state_before"
        ]["snapshot_sha256"]

        if (
            previous_state_after_hash is not None
            and current_before_hash
            != previous_state_after_hash
        ):
            raise BodyHistoryError(
                "Discontinuité corporelle détectée : "
                "state_before ne correspond pas au "
                "state_after précédent."
            )

        if entry.get("body_state_mutation_applied") is not False:
            raise BodyHistoryError(
                "L'inscription historique ne doit pas "
                "prétendre modifier l'état corporel."
            )

        if entry.get("subjective_state_claimed") is not False:
            raise BodyHistoryError(
                "Une entrée historique ne peut pas "
                "revendiquer un état subjectif."
            )

        if entry.get("external_action_performed") is not False:
            raise BodyHistoryError(
                "Une entrée historique ne peut pas "
                "revendiquer une action extérieure."
            )

        expected_entry_hash = _payload_hash(
            entry,
            "entry_sha256",
        )

        if entry.get("entry_sha256") != expected_entry_hash:
            raise BodyHistoryError(
                "Hash d'entrée historique invalide."
            )

        previous_entry_hash = entry[
            "entry_sha256"
        ]
        previous_state_after_hash = transformation[
            "state_after"
        ]["snapshot_sha256"]

    expected_registry_hash = _payload_hash(
        history,
        "registry_sha256",
    )

    if (
        history.get("registry_sha256")
        != expected_registry_hash
    ):
        raise BodyHistoryError(
            "Hash du registre historique invalide."
        )

    return history


def load_body_history(
    path: Path | str,
) -> dict[str, Any]:
    history_path = Path(path)

    if not history_path.exists():
        raise BodyHistoryError(
            f"Body history absent : {history_path}"
        )

    try:
        payload = json.loads(
            history_path.read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError) as error:
        raise BodyHistoryError(
            "Body history illisible ou corrompu."
        ) from error

    return validate_body_history(payload)


def _load_or_empty(
    path: Path,
    *,
    now: datetime | None,
) -> dict[str, Any]:
    if path.exists():
        return load_body_history(path)

    return build_empty_body_history(
        now=now
    )


def preview_body_transformation_append(
    path: Path | str,
    transformation: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Prépare une inscription sans écrire sur disque.
    """
    history_path = Path(path)

    try:
        validated_transformation = copy.deepcopy(
            validate_body_transformation(
                transformation
            )
        )
    except BodySchemaError as error:
        raise BodyHistoryError(
            "Transformation candidate invalide."
        ) from error

    history = _load_or_empty(
        history_path,
        now=now,
    )

    transformation_hash = validated_transformation[
        "transformation_sha256"
    ]

    for entry in history["entries"]:
        existing = entry["transformation"][
            "transformation_sha256"
        ]

        if existing == transformation_hash:
            return {
                "schema_version": 1,
                "identity": "Eliot-Jr",
                "mode": "preview",
                "status": "already_recorded",
                "history_path": str(history_path),
                "transformation_sha256": (
                    transformation_hash
                ),
                "entry_id": entry["entry_id"],
                "history_before_sha256": history[
                    "registry_sha256"
                ],
                "history_after_sha256": history[
                    "registry_sha256"
                ],
                "candidate_entry": None,
                "candidate_history": copy.deepcopy(
                    history
                ),
                "registry_mutation_applied": False,
                "external_action_performed": False,
                "subjective_state_claimed": False,
            }

    if history["entries"]:
        previous_transformation = history[
            "entries"
        ][-1]["transformation"]

        expected_before_hash = (
            previous_transformation[
                "state_after"
            ]["snapshot_sha256"]
        )

        actual_before_hash = (
            validated_transformation[
                "state_before"
            ]["snapshot_sha256"]
        )

        if actual_before_hash != expected_before_hash:
            raise BodyHistoryError(
                "La transformation candidate ne "
                "prolonge pas le dernier état connu."
            )

    timestamp = _utc_now(now)
    sequence = len(history["entries"]) + 1
    previous_hash = (
        history["entries"][-1]["entry_sha256"]
        if history["entries"]
        else None
    )

    entry: dict[str, Any] = {
        "sequence": sequence,
        "entry_id": (
            f"body_transformation_{sequence:06d}_"
            f"{transformation_hash[:12]}"
        ),
        "recorded_at_utc": timestamp,
        "previous_entry_sha256": previous_hash,
        "transformation": validated_transformation,
        "body_state_mutation_applied": False,
        "subjective_state_claimed": False,
        "external_action_performed": False,
    }

    entry["entry_sha256"] = _payload_hash(
        entry,
        "entry_sha256",
    )

    candidate_history = copy.deepcopy(history)
    candidate_history["entries"].append(entry)
    candidate_history["entry_count"] = len(
        candidate_history["entries"]
    )
    candidate_history["updated_at_utc"] = timestamp
    candidate_history["registry_sha256"] = (
        _payload_hash(
            candidate_history,
            "registry_sha256",
        )
    )

    validate_body_history(
        candidate_history
    )

    return {
        "schema_version": 1,
        "identity": "Eliot-Jr",
        "mode": "preview",
        "status": "append_ready",
        "history_path": str(history_path),
        "transformation_sha256": transformation_hash,
        "entry_id": entry["entry_id"],
        "history_before_sha256": history[
            "registry_sha256"
        ],
        "history_after_sha256": candidate_history[
            "registry_sha256"
        ],
        "candidate_entry": copy.deepcopy(entry),
        "candidate_history": candidate_history,
        "registry_mutation_applied": False,
        "external_action_performed": False,
        "subjective_state_claimed": False,
    }


def _write_json_atomic(
    path: Path,
    payload: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    file_descriptor, temporary_name = (
        tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
    )

    try:
        with os.fdopen(
            file_descriptor,
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
            os.unlink(
                temporary_name
            )
        except OSError:
            pass
        raise


def commit_body_transformation_append(
    path: Path | str,
    transformation: dict[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Inscrit explicitement une transformation validée.

    Aucun état corporel n'est modifié ici :
    seul le registre historique est écrit.
    """
    history_path = Path(path)

    preview = preview_body_transformation_append(
        history_path,
        transformation,
        now=now,
    )

    if preview["status"] == "already_recorded":
        result = copy.deepcopy(preview)
        result["mode"] = "commit"
        return result

    candidate_history = preview[
        "candidate_history"
    ]

    _write_json_atomic(
        history_path,
        candidate_history,
    )

    persisted = load_body_history(
        history_path
    )

    if (
        persisted["registry_sha256"]
        != candidate_history["registry_sha256"]
    ):
        raise BodyHistoryError(
            "La vérification post-écriture a échoué."
        )

    result = copy.deepcopy(preview)
    result["mode"] = "commit"
    result["status"] = "committed"
    result["registry_mutation_applied"] = True
    result["candidate_history"] = copy.deepcopy(
        persisted
    )

    return result
