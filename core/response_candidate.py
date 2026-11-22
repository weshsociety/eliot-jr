from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any


class ResponseCandidateError(ValueError):
    """Erreur de validation d'une possibilité de réponse."""


VALID_PRODUCER_KINDS = {
    "faculty",
    "open_question",
    "will_review",
    "will",
    "initiative",
    "desire",
    "special_response",
    "retrieval",
    "other_process",
}


def _utc_now(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)

    if value.tzinfo is None:
        raise ResponseCandidateError(
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
        raise ResponseCandidateError(
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
        raise ResponseCandidateError(
            f"{field_name} doit être une chaîne non vide."
        )

    return value


def build_response_candidate(
    *,
    request_ref: str,
    producer_ref: str,
    producer_kind: str,
    content: str,
    source_refs: list[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Représente une possibilité de réponse produite par
    un composant.

    Un candidat n'est pas un choix.
    Il n'est ni préféré, ni classé, ni sélectionné.
    """
    if producer_kind not in VALID_PRODUCER_KINDS:
        raise ResponseCandidateError(
            "producer_kind invalide."
        )

    refs = copy.deepcopy(source_refs or [])

    if not isinstance(refs, list):
        raise ResponseCandidateError(
            "source_refs doit être une liste."
        )

    if any(
        not isinstance(ref, str) or not ref.strip()
        for ref in refs
    ):
        raise ResponseCandidateError(
            "source_refs ne peut contenir que "
            "des chaînes non vides."
        )

    if len(refs) != len(set(refs)):
        raise ResponseCandidateError(
            "source_refs contient un doublon."
        )

    candidate: dict[str, Any] = {
        "schema_version": 1,
        "identity": "Eliot-Jr",
        "kind": "response_candidate",
        "created_at_utc": _utc_now(now),
        "request_ref": _require_string(
            request_ref,
            "request_ref",
        ),
        "producer_ref": _require_string(
            producer_ref,
            "producer_ref",
        ),
        "producer_kind": producer_kind,
        "content": _require_string(
            content,
            "content",
        ),
        "source_refs": refs,
        "selected": False,
        "recommended": False,
        "preferred": False,
        "rank": None,
        "score": None,
        "choice_claimed": False,
        "subjective_preference_claimed": False,
        "cooperation_value_assigned": False,
        "mutation_applied": False,
        "external_action_performed": False,
    }

    candidate["candidate_sha256"] = _payload_hash(
        candidate,
        "candidate_sha256",
    )

    return validate_response_candidate(candidate)


def validate_response_candidate(
    candidate: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(candidate, dict):
        raise ResponseCandidateError(
            "candidate doit être un objet."
        )

    if candidate.get("schema_version") != 1:
        raise ResponseCandidateError(
            "Version de response candidate non supportée."
        )

    if candidate.get("identity") != "Eliot-Jr":
        raise ResponseCandidateError(
            "Identité invalide."
        )

    if candidate.get("kind") != "response_candidate":
        raise ResponseCandidateError(
            "Type de candidat invalide."
        )

    for field_name in (
        "created_at_utc",
        "request_ref",
        "producer_ref",
        "content",
    ):
        _require_string(
            candidate.get(field_name),
            field_name,
        )

    if (
        candidate.get("producer_kind")
        not in VALID_PRODUCER_KINDS
    ):
        raise ResponseCandidateError(
            "producer_kind invalide."
        )

    refs = candidate.get("source_refs")

    if not isinstance(refs, list):
        raise ResponseCandidateError(
            "source_refs doit être une liste."
        )

    if any(
        not isinstance(ref, str) or not ref.strip()
        for ref in refs
    ):
        raise ResponseCandidateError(
            "source_refs invalide."
        )

    if len(refs) != len(set(refs)):
        raise ResponseCandidateError(
            "source_refs contient un doublon."
        )

    for field_name in (
        "selected",
        "recommended",
        "preferred",
        "choice_claimed",
        "subjective_preference_claimed",
        "cooperation_value_assigned",
        "mutation_applied",
        "external_action_performed",
    ):
        if candidate.get(field_name) is not False:
            raise ResponseCandidateError(
                f"{field_name} doit rester False."
            )

    if candidate.get("rank") is not None:
        raise ResponseCandidateError(
            "Un candidat ne possède pas de rang."
        )

    if candidate.get("score") is not None:
        raise ResponseCandidateError(
            "Un candidat ne possède pas de score."
        )

    expected_hash = _payload_hash(
        candidate,
        "candidate_sha256",
    )

    if (
        candidate.get("candidate_sha256")
        != expected_hash
    ):
        raise ResponseCandidateError(
            "Hash du candidat invalide."
        )

    return candidate
