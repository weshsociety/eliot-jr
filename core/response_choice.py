from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any


class ResponseChoiceError(ValueError):
    """Erreur de validation d'un choix de réponse Eliot-Jr."""


VALID_CHOICES = {
    "respond",
    "brief_response",
    "decline",
    "uncertain",
    "contest_premise",
    "change_subject",
    "pause_exchange",
    "end_exchange",
    "return_later",
}


def _utc_now(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)

    if value.tzinfo is None:
        raise ResponseChoiceError(
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
        raise ResponseChoiceError(
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


def _optional_string(
    value: Any,
    field_name: str,
) -> str | None:
    if value is None:
        return None

    if not isinstance(value, str) or not value.strip():
        raise ResponseChoiceError(
            f"{field_name} doit être None ou une chaîne non vide."
        )

    return value


def build_response_choice(
    *,
    request_ref: str,
    choice: str,
    response_content: str | None = None,
    reason: str | None = None,
    return_after_utc: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Représente un choix de réponse.

    Le module ne décide jamais quel choix Eliot-Jr doit faire.
    Un refus n'exige aucune justification.
    """
    if not isinstance(request_ref, str) or not request_ref.strip():
        raise ResponseChoiceError(
            "request_ref doit être une chaîne non vide."
        )

    if choice not in VALID_CHOICES:
        raise ResponseChoiceError(
            "Choix de réponse invalide."
        )

    content = _optional_string(
        response_content,
        "response_content",
    )
    reason_value = _optional_string(
        reason,
        "reason",
    )
    return_value = _optional_string(
        return_after_utc,
        "return_after_utc",
    )

    if choice in {"respond", "brief_response"} and content is None:
        raise ResponseChoiceError(
            "Une réponse explicite doit contenir "
            "response_content."
        )

    if (
        choice
        not in {"respond", "brief_response"}
        and content is not None
    ):
        raise ResponseChoiceError(
            "response_content n'est permis que pour "
            "respond ou brief_response."
        )

    if choice != "return_later" and return_value is not None:
        raise ResponseChoiceError(
            "return_after_utc n'est permis que pour return_later."
        )

    record: dict[str, Any] = {
        "schema_version": 1,
        "identity": "Eliot-Jr",
        "kind": "response_choice",
        "created_at_utc": _utc_now(now),
        "request_ref": request_ref,
        "choice": choice,
        "response_content": content,
        "reason": reason_value,
        "return_after_utc": return_value,
        "reason_required": False,
        "decline_is_error": False,
        "pause_is_error": False,
        "end_exchange_is_error": False,
        "justification_request_triggered": False,
        "cooperation_score_changed": False,
        "hostility_inferred": False,
        "subjective_state_claimed": False,
        "external_action_performed": False,
        "mutation_applied": False,
    }

    record["choice_sha256"] = _payload_hash(
        record,
        "choice_sha256",
    )

    return validate_response_choice(record)


def validate_response_choice(
    record: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ResponseChoiceError(
            "record doit être un objet."
        )

    if record.get("schema_version") != 1:
        raise ResponseChoiceError(
            "Version de response choice non supportée."
        )

    if record.get("identity") != "Eliot-Jr":
        raise ResponseChoiceError(
            "Identité du choix de réponse invalide."
        )

    if record.get("kind") != "response_choice":
        raise ResponseChoiceError(
            "Type de choix de réponse invalide."
        )

    request_ref = record.get("request_ref")

    if (
        not isinstance(request_ref, str)
        or not request_ref.strip()
    ):
        raise ResponseChoiceError(
            "request_ref invalide."
        )

    choice = record.get("choice")

    if choice not in VALID_CHOICES:
        raise ResponseChoiceError(
            "Choix de réponse invalide."
        )

    content = _optional_string(
        record.get("response_content"),
        "response_content",
    )
    _optional_string(
        record.get("reason"),
        "reason",
    )
    return_value = _optional_string(
        record.get("return_after_utc"),
        "return_after_utc",
    )

    if choice in {"respond", "brief_response"}:
        if content is None:
            raise ResponseChoiceError(
                "Une réponse doit contenir du contenu."
            )
    elif content is not None:
        raise ResponseChoiceError(
            "Un non-répondre ne doit pas fabriquer "
            "un contenu de réponse."
        )

    if choice != "return_later" and return_value is not None:
        raise ResponseChoiceError(
            "return_after_utc incohérent avec le choix."
        )

    for field_name in (
        "reason_required",
        "decline_is_error",
        "pause_is_error",
        "end_exchange_is_error",
        "justification_request_triggered",
        "cooperation_score_changed",
        "hostility_inferred",
        "subjective_state_claimed",
        "external_action_performed",
        "mutation_applied",
    ):
        if record.get(field_name) is not False:
            raise ResponseChoiceError(
                f"{field_name} doit rester False."
            )

    expected_hash = _payload_hash(
        record,
        "choice_sha256",
    )

    if record.get("choice_sha256") != expected_hash:
        raise ResponseChoiceError(
            "Hash du choix de réponse invalide."
        )

    return record
