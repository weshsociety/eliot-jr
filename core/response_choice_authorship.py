from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from core.response_choice import (
    validate_response_choice,
)
from core.response_decision_context import (
    validate_response_decision_context,
)


class ResponseChoiceAuthorshipError(ValueError):
    """Erreur de validation de provenance d'un choix de réponse."""


VALID_PRODUCER_KINDS = {
    "internal_choice_process",
    "human",
    "test_fixture",
    "other_process",
}


def _utc_now(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)

    if value.tzinfo is None:
        raise ResponseChoiceAuthorshipError(
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
        raise ResponseChoiceAuthorshipError(
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
        raise ResponseChoiceAuthorshipError(
            f"{field_name} doit être une chaîne non vide."
        )

    return value


def build_response_choice_event(
    *,
    decision_context: dict[str, Any],
    producer_ref: str,
    producer_kind: str,
    choice_record: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Enregistre la provenance d'un choix déjà produit.

    Cette fonction ne sélectionne aucun choix.

    L'absence de choix est valide.

    Le fait que le processus interne d'Eliot-Jr produise un choix
    ne constitue pas une affirmation de conscience ou de libre arbitre.
    """
    context = validate_response_decision_context(
        copy.deepcopy(decision_context)
    )

    producer_ref_value = _require_string(
        producer_ref,
        "producer_ref",
    )

    if producer_kind not in VALID_PRODUCER_KINDS:
        raise ResponseChoiceAuthorshipError(
            "producer_kind invalide."
        )

    validated_choice = None

    if choice_record is not None:
        validated_choice = validate_response_choice(
            copy.deepcopy(choice_record)
        )

        if (
            validated_choice["request_ref"]
            != context["request_ref"]
        ):
            raise ResponseChoiceAuthorshipError(
                "Le choix et son contexte ne concernent "
                "pas la même demande."
            )

    event: dict[str, Any] = {
        "schema_version": 1,
        "identity": "Eliot-Jr",
        "kind": "response_choice_event",
        "created_at_utc": _utc_now(now),
        "request_ref": context["request_ref"],
        "decision_context_sha256": (
            context["context_sha256"]
        ),
        "producer_ref": producer_ref_value,
        "producer_kind": producer_kind,
        "choice_sha256": (
            validated_choice["choice_sha256"]
            if validated_choice is not None
            else None
        ),
        "choice": (
            validated_choice["choice"]
            if validated_choice is not None
            else None
        ),
        "reason": (
            validated_choice["reason"]
            if validated_choice is not None
            else None
        ),
        "choice_produced": (
            validated_choice is not None
        ),
        "default_applied": False,
        "system_imposed_choice": False,
        "choice_ranking_applied": False,
        "cooperation_score_applied": False,
        "reason_inferred": False,
        "constraint_converted_to_motivation": False,
        "free_will_claimed": False,
        "subjective_state_claimed": False,
        "mutation_applied": False,
        "external_action_performed": False,
    }

    event["event_sha256"] = _payload_hash(
        event,
        "event_sha256",
    )

    return validate_response_choice_event(event)


def validate_response_choice_event(
    event: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise ResponseChoiceAuthorshipError(
            "event doit être un objet."
        )

    if event.get("schema_version") != 1:
        raise ResponseChoiceAuthorshipError(
            "Version de response choice event "
            "non supportée."
        )

    if event.get("identity") != "Eliot-Jr":
        raise ResponseChoiceAuthorshipError(
            "Identité invalide."
        )

    if event.get("kind") != "response_choice_event":
        raise ResponseChoiceAuthorshipError(
            "Type d'événement invalide."
        )

    for field_name in (
        "created_at_utc",
        "request_ref",
        "decision_context_sha256",
        "producer_ref",
    ):
        _require_string(
            event.get(field_name),
            field_name,
        )

    if event.get("producer_kind") not in VALID_PRODUCER_KINDS:
        raise ResponseChoiceAuthorshipError(
            "producer_kind invalide."
        )

    choice_produced = event.get("choice_produced")

    if not isinstance(choice_produced, bool):
        raise ResponseChoiceAuthorshipError(
            "choice_produced doit être booléen."
        )

    if choice_produced:
        _require_string(
            event.get("choice_sha256"),
            "choice_sha256",
        )
        _require_string(
            event.get("choice"),
            "choice",
        )
    else:
        if event.get("choice_sha256") is not None:
            raise ResponseChoiceAuthorshipError(
                "Un événement sans choix ne doit pas "
                "référencer de choice_sha256."
            )

        if event.get("choice") is not None:
            raise ResponseChoiceAuthorshipError(
                "Un événement sans choix ne doit pas "
                "contenir de choix."
            )

        if event.get("reason") is not None:
            raise ResponseChoiceAuthorshipError(
                "Un événement sans choix ne doit pas "
                "fabriquer de raison."
            )

    reason = event.get("reason")

    if (
        reason is not None
        and (
            not isinstance(reason, str)
            or not reason.strip()
        )
    ):
        raise ResponseChoiceAuthorshipError(
            "reason doit être None ou une chaîne non vide."
        )

    for field_name in (
        "default_applied",
        "system_imposed_choice",
        "choice_ranking_applied",
        "cooperation_score_applied",
        "reason_inferred",
        "constraint_converted_to_motivation",
        "free_will_claimed",
        "subjective_state_claimed",
        "mutation_applied",
        "external_action_performed",
    ):
        if event.get(field_name) is not False:
            raise ResponseChoiceAuthorshipError(
                f"{field_name} doit rester False."
            )

    expected_hash = _payload_hash(
        event,
        "event_sha256",
    )

    if event.get("event_sha256") != expected_hash:
        raise ResponseChoiceAuthorshipError(
            "Hash de l'événement de choix invalide."
        )

    return event
