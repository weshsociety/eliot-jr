from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from core.dialogue_request import (
    validate_dialogue_request,
)
from core.response_candidate_set import (
    validate_response_candidate_set,
)
from core.response_decision_context import (
    validate_response_decision_context,
)


class ResponseDeliberationPacketError(ValueError):
    """Erreur de validation d'un paquet de délibération."""


def _utc_now(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)

    if value.tzinfo is None:
        raise ResponseDeliberationPacketError(
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
        raise ResponseDeliberationPacketError(
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


def build_response_deliberation_packet(
    *,
    dialogue_request: dict[str, Any],
    candidate_set: dict[str, Any],
    decision_context: dict[str, Any],
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Fige l'état disponible avant un éventuel acte de choix.

    Ce paquet :
    - ne choisit rien ;
    - ne classe rien ;
    - ne recommande rien ;
    - ne fabrique aucune motivation.
    """
    request = validate_dialogue_request(
        copy.deepcopy(dialogue_request)
    )

    candidates = validate_response_candidate_set(
        copy.deepcopy(candidate_set)
    )

    context = validate_response_decision_context(
        copy.deepcopy(decision_context)
    )

    request_ref = request["request_ref"]

    if candidates["request_ref"] != request_ref:
        raise ResponseDeliberationPacketError(
            "L'ensemble de candidats appartient "
            "à une autre demande."
        )

    if context["request_ref"] != request_ref:
        raise ResponseDeliberationPacketError(
            "Le contexte de décision appartient "
            "à une autre demande."
        )

    packet: dict[str, Any] = {
        "schema_version": 1,
        "identity": "Eliot-Jr",
        "kind": "response_deliberation_packet",
        "created_at_utc": _utc_now(now),
        "request_ref": request_ref,
        "request_sha256": request["request_sha256"],
        "candidate_set_sha256": (
            candidates["candidate_set_sha256"]
        ),
        "decision_context_sha256": (
            context["context_sha256"]
        ),
        "dialogue_request": request,
        "candidate_set": candidates,
        "decision_context": context,
        "candidate_count": candidates[
            "candidate_count"
        ],
        "selected_candidate_sha256": None,
        "selected_choice_sha256": None,
        "selection_performed": False,
        "choice_produced": False,
        "selection_required": False,
        "default_applied": False,
        "ranking_applied": False,
        "scoring_applied": False,
        "recommendation_applied": False,
        "positional_priority_applied": False,
        "reason_inferred": False,
        "constraint_converted_to_motivation": False,
        "subjective_state_claimed": False,
        "free_will_claimed": False,
        "mutation_applied": False,
        "external_action_performed": False,
    }

    packet["packet_sha256"] = _payload_hash(
        packet,
        "packet_sha256",
    )

    return validate_response_deliberation_packet(
        packet
    )


def validate_response_deliberation_packet(
    packet: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(packet, dict):
        raise ResponseDeliberationPacketError(
            "packet doit être un objet."
        )

    if packet.get("schema_version") != 1:
        raise ResponseDeliberationPacketError(
            "Version de deliberation packet "
            "non supportée."
        )

    if packet.get("identity") != "Eliot-Jr":
        raise ResponseDeliberationPacketError(
            "Identité invalide."
        )

    if (
        packet.get("kind")
        != "response_deliberation_packet"
    ):
        raise ResponseDeliberationPacketError(
            "Type de paquet invalide."
        )

    request = validate_dialogue_request(
        copy.deepcopy(
            packet.get("dialogue_request")
        )
    )

    candidates = validate_response_candidate_set(
        copy.deepcopy(
            packet.get("candidate_set")
        )
    )

    context = validate_response_decision_context(
        copy.deepcopy(
            packet.get("decision_context")
        )
    )

    request_ref = request["request_ref"]

    if packet.get("request_ref") != request_ref:
        raise ResponseDeliberationPacketError(
            "request_ref incohérent."
        )

    if candidates["request_ref"] != request_ref:
        raise ResponseDeliberationPacketError(
            "candidate_set lié à une autre demande."
        )

    if context["request_ref"] != request_ref:
        raise ResponseDeliberationPacketError(
            "decision_context lié à une autre demande."
        )

    if (
        packet.get("request_sha256")
        != request["request_sha256"]
    ):
        raise ResponseDeliberationPacketError(
            "Empreinte de demande incohérente."
        )

    if (
        packet.get("candidate_set_sha256")
        != candidates["candidate_set_sha256"]
    ):
        raise ResponseDeliberationPacketError(
            "Empreinte de candidats incohérente."
        )

    if (
        packet.get("decision_context_sha256")
        != context["context_sha256"]
    ):
        raise ResponseDeliberationPacketError(
            "Empreinte du contexte incohérente."
        )

    if (
        packet.get("candidate_count")
        != candidates["candidate_count"]
    ):
        raise ResponseDeliberationPacketError(
            "candidate_count incohérent."
        )

    if (
        packet.get("selected_candidate_sha256")
        is not None
    ):
        raise ResponseDeliberationPacketError(
            "Le paquet pré-choix ne peut pas "
            "sélectionner de candidat."
        )

    if packet.get("selected_choice_sha256") is not None:
        raise ResponseDeliberationPacketError(
            "Le paquet pré-choix ne peut pas "
            "contenir de choix."
        )

    for field_name in (
        "selection_performed",
        "choice_produced",
        "selection_required",
        "default_applied",
        "ranking_applied",
        "scoring_applied",
        "recommendation_applied",
        "positional_priority_applied",
        "reason_inferred",
        "constraint_converted_to_motivation",
        "subjective_state_claimed",
        "free_will_claimed",
        "mutation_applied",
        "external_action_performed",
    ):
        if packet.get(field_name) is not False:
            raise ResponseDeliberationPacketError(
                f"{field_name} doit rester False."
            )

    expected_hash = _payload_hash(
        packet,
        "packet_sha256",
    )

    if packet.get("packet_sha256") != expected_hash:
        raise ResponseDeliberationPacketError(
            "Hash du paquet de délibération invalide."
        )

    return packet
