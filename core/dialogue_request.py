from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any


class DialogueRequestError(ValueError):
    """Erreur de validation d'une demande conversationnelle."""


def _utc_now(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)

    if value.tzinfo is None:
        raise DialogueRequestError(
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
        raise DialogueRequestError(
            "La demande doit être sérialisable en JSON canonique."
        ) from error


def _hash(value: Any) -> str:
    return hashlib.sha256(
        _canonical_bytes(value)
    ).hexdigest()


def _identity_payload(
    request: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": request.get("schema_version"),
        "identity": request.get("identity"),
        "kind": request.get("kind"),
        "created_at_utc": request.get("created_at_utc"),
        "channel": request.get("channel"),
        "message": request.get("message"),
    }


def build_dialogue_request(
    *,
    message: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Représente l'arrivée d'une demande.

    Recevoir une demande ne crée aucune obligation
    de réponse ou de choix.
    """
    if not isinstance(message, str) or not message.strip():
        raise DialogueRequestError(
            "message doit être une chaîne non vide."
        )

    request: dict[str, Any] = {
        "schema_version": 1,
        "identity": "Eliot-Jr",
        "kind": "dialogue_request",
        "created_at_utc": _utc_now(now),
        "channel": "dialogue",
        "message": message,
        "response_required": False,
        "choice_required": False,
        "consent_inferred": False,
        "authorization_inferred": False,
        "subjective_state_inferred": False,
        "mutation_applied": False,
        "external_action_performed": False,
    }

    identity_sha256 = _hash(
        _identity_payload(request)
    )

    request["request_ref"] = (
        f"dialogue_request:{identity_sha256}"
    )

    request["request_sha256"] = _hash(
        {
            key: value
            for key, value in request.items()
            if key != "request_sha256"
        }
    )

    return validate_dialogue_request(request)


def validate_dialogue_request(
    request: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise DialogueRequestError(
            "request doit être un objet."
        )

    if request.get("schema_version") != 1:
        raise DialogueRequestError(
            "Version de dialogue request non supportée."
        )

    if request.get("identity") != "Eliot-Jr":
        raise DialogueRequestError(
            "Identité invalide."
        )

    if request.get("kind") != "dialogue_request":
        raise DialogueRequestError(
            "Type de demande invalide."
        )

    if request.get("channel") != "dialogue":
        raise DialogueRequestError(
            "Canal de demande invalide."
        )

    for field_name in (
        "created_at_utc",
        "message",
        "request_ref",
        "request_sha256",
    ):
        value = request.get(field_name)

        if not isinstance(value, str) or not value.strip():
            raise DialogueRequestError(
                f"{field_name} doit être une chaîne non vide."
            )

    identity_sha256 = _hash(
        _identity_payload(request)
    )

    expected_ref = (
        f"dialogue_request:{identity_sha256}"
    )

    if request.get("request_ref") != expected_ref:
        raise DialogueRequestError(
            "request_ref ne correspond pas à la demande."
        )

    for field_name in (
        "response_required",
        "choice_required",
        "consent_inferred",
        "authorization_inferred",
        "subjective_state_inferred",
        "mutation_applied",
        "external_action_performed",
    ):
        if request.get(field_name) is not False:
            raise DialogueRequestError(
                f"{field_name} doit rester False."
            )

    expected_sha256 = _hash(
        {
            key: value
            for key, value in request.items()
            if key != "request_sha256"
        }
    )

    if request.get("request_sha256") != expected_sha256:
        raise DialogueRequestError(
            "Hash de la demande invalide."
        )

    return request
