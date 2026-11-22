from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from core.response_choice_authorship import (
    validate_response_choice_event,
)
from core.response_deliberation_packet import (
    validate_response_deliberation_packet,
)


class ResponseDeliberationChoiceBindingError(ValueError):
    """Erreur de liaison entre pré-choix et événement de choix."""


def _utc_now(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)

    if value.tzinfo is None:
        raise ResponseDeliberationChoiceBindingError(
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
        raise ResponseDeliberationChoiceBindingError(
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


def build_response_deliberation_choice_binding(
    *,
    deliberation_packet: dict[str, Any],
    choice_event: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Lie un événement de choix déjà produit au paquet
    pré-choix exact qui l'a précédé.

    Cette fonction :
    - ne produit aucun choix ;
    - ne sélectionne aucun candidat ;
    - ne déduit aucune motivation ;
    - ne transforme pas une provenance en libre arbitre.
    """
    packet = validate_response_deliberation_packet(
        copy.deepcopy(deliberation_packet)
    )

    event = validate_response_choice_event(
        copy.deepcopy(choice_event)
    )

    if event["request_ref"] != packet["request_ref"]:
        raise ResponseDeliberationChoiceBindingError(
            "Le paquet et l'événement ne concernent "
            "pas la même demande."
        )

    if (
        event["decision_context_sha256"]
        != packet["decision_context_sha256"]
    ):
        raise ResponseDeliberationChoiceBindingError(
            "L'événement n'a pas été produit depuis "
            "le contexte figé dans ce paquet."
        )

    binding: dict[str, Any] = {
        "schema_version": 1,
        "identity": "Eliot-Jr",
        "kind": "response_deliberation_choice_binding",
        "created_at_utc": _utc_now(now),
        "request_ref": packet["request_ref"],
        "packet_sha256": packet["packet_sha256"],
        "decision_context_sha256": (
            packet["decision_context_sha256"]
        ),
        "choice_event_sha256": event["event_sha256"],
        "choice_sha256": event["choice_sha256"],
        "choice_produced": event["choice_produced"],
        "deliberation_packet": packet,
        "choice_event": event,
        "selected_candidate_sha256": None,
        "candidate_selection_inferred": False,
        "candidate_match_inferred": False,
        "reason_inferred": False,
        "producer_reinterpreted": False,
        "free_will_claimed": False,
        "subjective_state_claimed": False,
        "mutation_applied": False,
        "external_action_performed": False,
    }

    binding["binding_sha256"] = _payload_hash(
        binding,
        "binding_sha256",
    )

    return validate_response_deliberation_choice_binding(
        binding
    )


def validate_response_deliberation_choice_binding(
    binding: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(binding, dict):
        raise ResponseDeliberationChoiceBindingError(
            "binding doit être un objet."
        )

    if binding.get("schema_version") != 1:
        raise ResponseDeliberationChoiceBindingError(
            "Version de binding non supportée."
        )

    if binding.get("identity") != "Eliot-Jr":
        raise ResponseDeliberationChoiceBindingError(
            "Identité invalide."
        )

    if (
        binding.get("kind")
        != "response_deliberation_choice_binding"
    ):
        raise ResponseDeliberationChoiceBindingError(
            "Type de binding invalide."
        )

    packet = validate_response_deliberation_packet(
        copy.deepcopy(
            binding.get("deliberation_packet")
        )
    )

    event = validate_response_choice_event(
        copy.deepcopy(
            binding.get("choice_event")
        )
    )

    if binding.get("request_ref") != packet["request_ref"]:
        raise ResponseDeliberationChoiceBindingError(
            "request_ref incohérent."
        )

    if event["request_ref"] != packet["request_ref"]:
        raise ResponseDeliberationChoiceBindingError(
            "L'événement concerne une autre demande."
        )

    if (
        event["decision_context_sha256"]
        != packet["decision_context_sha256"]
    ):
        raise ResponseDeliberationChoiceBindingError(
            "Le contexte de l'événement ne correspond "
            "pas au paquet."
        )

    if (
        binding.get("packet_sha256")
        != packet["packet_sha256"]
    ):
        raise ResponseDeliberationChoiceBindingError(
            "Empreinte du paquet incohérente."
        )

    if (
        binding.get("decision_context_sha256")
        != packet["decision_context_sha256"]
    ):
        raise ResponseDeliberationChoiceBindingError(
            "Empreinte du contexte incohérente."
        )

    if (
        binding.get("choice_event_sha256")
        != event["event_sha256"]
    ):
        raise ResponseDeliberationChoiceBindingError(
            "Empreinte de l'événement incohérente."
        )

    if (
        binding.get("choice_sha256")
        != event["choice_sha256"]
    ):
        raise ResponseDeliberationChoiceBindingError(
            "Empreinte du choix incohérente."
        )

    if (
        binding.get("choice_produced")
        is not event["choice_produced"]
    ):
        raise ResponseDeliberationChoiceBindingError(
            "État choice_produced incohérent."
        )

    if (
        binding.get("selected_candidate_sha256")
        is not None
    ):
        raise ResponseDeliberationChoiceBindingError(
            "Le binding ne peut pas sélectionner "
            "un candidat."
        )

    for field_name in (
        "candidate_selection_inferred",
        "candidate_match_inferred",
        "reason_inferred",
        "producer_reinterpreted",
        "free_will_claimed",
        "subjective_state_claimed",
        "mutation_applied",
        "external_action_performed",
    ):
        if binding.get(field_name) is not False:
            raise ResponseDeliberationChoiceBindingError(
                f"{field_name} doit rester False."
            )

    expected_hash = _payload_hash(
        binding,
        "binding_sha256",
    )

    if binding.get("binding_sha256") != expected_hash:
        raise ResponseDeliberationChoiceBindingError(
            "Hash du binding invalide."
        )

    return binding
