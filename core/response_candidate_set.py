from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from core.response_candidate import (
    validate_response_candidate,
)


class ResponseCandidateSetError(ValueError):
    """Erreur de validation d'un ensemble de candidats."""


def _utc_now(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)

    if value.tzinfo is None:
        raise ResponseCandidateSetError(
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
        raise ResponseCandidateSetError(
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
        raise ResponseCandidateSetError(
            f"{field_name} doit être une chaîne non vide."
        )

    return value


def build_response_candidate_set(
    *,
    request_ref: str,
    candidates: list[dict[str, Any]] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Regroupe des possibilités de réponse sans leur attribuer
    d'ordre, de rang, de score ou de gagnant.

    L'ordre dans lequel les candidats sont fournis ne possède
    aucune signification.
    """
    request_ref_value = _require_string(
        request_ref,
        "request_ref",
    )

    candidate_values = copy.deepcopy(
        candidates or []
    )

    if not isinstance(candidate_values, list):
        raise ResponseCandidateSetError(
            "candidates doit être une liste d'entrée."
        )

    candidates_by_sha256: dict[
        str,
        dict[str, Any],
    ] = {}

    for raw_candidate in candidate_values:
        candidate = validate_response_candidate(
            raw_candidate
        )

        if candidate["request_ref"] != request_ref_value:
            raise ResponseCandidateSetError(
                "Tous les candidats doivent concerner la même demande."
            )

        candidate_sha256 = candidate["candidate_sha256"]

        if candidate_sha256 in candidates_by_sha256:
            raise ResponseCandidateSetError(
                "Un même candidat ne peut pas être présent deux fois."
            )

        candidates_by_sha256[candidate_sha256] = candidate

    candidate_set: dict[str, Any] = {
        "schema_version": 1,
        "identity": "Eliot-Jr",
        "kind": "response_candidate_set",
        "created_at_utc": _utc_now(now),
        "request_ref": request_ref_value,
        "candidate_count": len(candidates_by_sha256),
        "candidates_by_sha256": candidates_by_sha256,
        "ordering_semantics": "none",
        "selected_candidate_sha256": None,
        "default_candidate_sha256": None,
        "selection_required": False,
        "ranking_enabled": False,
        "scores_enabled": False,
        "preferred_candidate_assigned": False,
        "automatic_selection_enabled": False,
        "positional_priority_enabled": False,
        "choice_claimed": False,
        "mutation_applied": False,
        "external_action_performed": False,
    }

    candidate_set["candidate_set_sha256"] = _payload_hash(
        candidate_set,
        "candidate_set_sha256",
    )

    return validate_response_candidate_set(candidate_set)


def validate_response_candidate_set(
    candidate_set: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(candidate_set, dict):
        raise ResponseCandidateSetError(
            "candidate_set doit être un objet."
        )

    if candidate_set.get("schema_version") != 1:
        raise ResponseCandidateSetError(
            "Version de candidate set non supportée."
        )

    if candidate_set.get("identity") != "Eliot-Jr":
        raise ResponseCandidateSetError(
            "Identité invalide."
        )

    if candidate_set.get("kind") != "response_candidate_set":
        raise ResponseCandidateSetError(
            "Type d'ensemble invalide."
        )

    for field_name in (
        "created_at_utc",
        "request_ref",
    ):
        _require_string(
            candidate_set.get(field_name),
            field_name,
        )

    candidates_by_sha256 = candidate_set.get(
        "candidates_by_sha256"
    )

    if not isinstance(candidates_by_sha256, dict):
        raise ResponseCandidateSetError(
            "candidates_by_sha256 doit être un objet."
        )

    for candidate_sha256, raw_candidate in (
        candidates_by_sha256.items()
    ):
        _require_string(
            candidate_sha256,
            "candidate_sha256",
        )

        candidate = validate_response_candidate(
            raw_candidate
        )

        if candidate["candidate_sha256"] != candidate_sha256:
            raise ResponseCandidateSetError(
                "La clé d'un candidat doit être son empreinte exacte."
            )

        if candidate["request_ref"] != candidate_set["request_ref"]:
            raise ResponseCandidateSetError(
                "Un candidat appartient à une autre demande."
            )

    candidate_count = candidate_set.get(
        "candidate_count"
    )

    if (
        isinstance(candidate_count, bool)
        or not isinstance(candidate_count, int)
        or candidate_count < 0
    ):
        raise ResponseCandidateSetError(
            "candidate_count invalide."
        )

    if candidate_count != len(candidates_by_sha256):
        raise ResponseCandidateSetError(
            "candidate_count ne correspond pas aux candidats présents."
        )

    if candidate_set.get("ordering_semantics") != "none":
        raise ResponseCandidateSetError(
            "L'ordre des candidats ne doit porter aucune signification."
        )

    if candidate_set.get("selected_candidate_sha256") is not None:
        raise ResponseCandidateSetError(
            "L'ensemble ne doit sélectionner aucun candidat."
        )

    if candidate_set.get("default_candidate_sha256") is not None:
        raise ResponseCandidateSetError(
            "Aucun candidat par défaut n'est autorisé."
        )

    for field_name in (
        "selection_required",
        "ranking_enabled",
        "scores_enabled",
        "preferred_candidate_assigned",
        "automatic_selection_enabled",
        "positional_priority_enabled",
        "choice_claimed",
        "mutation_applied",
        "external_action_performed",
    ):
        if candidate_set.get(field_name) is not False:
            raise ResponseCandidateSetError(
                f"{field_name} doit rester False."
            )

    expected_hash = _payload_hash(
        candidate_set,
        "candidate_set_sha256",
    )

    if candidate_set.get("candidate_set_sha256") != expected_hash:
        raise ResponseCandidateSetError(
            "Hash de l'ensemble de candidats invalide."
        )

    return candidate_set
