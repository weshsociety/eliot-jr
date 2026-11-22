from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from core.response_choice import VALID_CHOICES


class ResponseDecisionContextError(ValueError):
    """Erreur de validation d'un espace de décision de réponse."""


DECISION_CHOICES = (
    "respond",
    "brief_response",
    "decline",
    "uncertain",
    "contest_premise",
    "change_subject",
    "pause_exchange",
    "end_exchange",
    "return_later",
)


if set(DECISION_CHOICES) != set(VALID_CHOICES):
    raise RuntimeError(
        "Les choix de décision et de réponse divergent."
    )


def _utc_now(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)

    if value.tzinfo is None:
        raise ResponseDecisionContextError(
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
        raise ResponseDecisionContextError(
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
        raise ResponseDecisionContextError(
            f"{field_name} doit être une chaîne non vide."
        )

    return value


def _require_mapping(
    value: Any,
    field_name: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ResponseDecisionContextError(
            f"{field_name} doit être un objet."
        )

    _canonical_bytes(value)
    return value



_FORBIDDEN_REQUEST_CONTEXT_KEYS = frozenset({
    "automatic_selection_enabled",
    "choice_required",
    "choice_score",
    "choices_ranked",
    "cooperation_optimization",
    "cooperation_score",
    "default_choice",
    "operational_weight",
    "preferred_choice",
    "preferred_choice_assigned",
    "priority",
    "priority_score",
    "rank",
    "ranking",
    "reason_required",
    "recommended_choice",
    "refusal_penalty_enabled",
    "refusal_score",
    "response_score",
    "score",
    "selected_choice",
    "selection_applied",
    "selection_score",
    "weight",
})


def _normalise_context_key(value: str) -> str:
    return (
        value.strip()
        .lower()
        .replace("-", "_")
        .replace(" ", "_")
    )


def _validate_request_context_no_hidden_choice_influence(
    value: Any,
    field_name: str,
) -> Any:
    """
    Refuse les métadonnées qui pourraient piloter silencieusement
    un choix depuis request_context.

    Le contenu externe reste autorisé : une promotion, une opinion,
    un texte ou un nombre peuvent être présents comme informations.
    Ce sont les champs de classement, poids, recommandation ou
    sélection cachée qui sont interdits.
    """
    if isinstance(value, dict):
        for raw_key, child in value.items():
            if not isinstance(raw_key, str) or not raw_key.strip():
                raise ResponseDecisionContextError(
                    f"{field_name} contient une clé invalide."
                )

            key = _normalise_context_key(raw_key)

            if (
                key in _FORBIDDEN_REQUEST_CONTEXT_KEYS
                or key.endswith("_score")
                or key.endswith("_weight")
                or key.endswith("_priority")
                or key.endswith("_rank")
                or key.endswith("_ranking")
            ):
                raise ResponseDecisionContextError(
                    "Métadonnée de pilotage interdite dans "
                    f"{field_name}: {raw_key}"
                )

            _validate_request_context_no_hidden_choice_influence(
                child,
                f"{field_name}.{raw_key}",
            )

        return value

    if isinstance(value, list):
        for index, child in enumerate(value):
            _validate_request_context_no_hidden_choice_influence(
                child,
                f"{field_name}[{index}]",
            )

    return value


def _require_unique_string_list(
    value: Any,
    field_name: str,
) -> list[str]:
    if not isinstance(value, list):
        raise ResponseDecisionContextError(
            f"{field_name} doit être une liste."
        )

    seen: set[str] = set()

    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ResponseDecisionContextError(
                f"{field_name} ne peut contenir que "
                "des chaînes non vides."
            )

        if item in seen:
            raise ResponseDecisionContextError(
                f"{field_name} contient un doublon."
            )

        seen.add(item)

    return value


def build_response_decision_context(
    *,
    request_ref: str,
    request_context: dict[str, Any] | None = None,
    available_internal_refs: list[str] | None = None,
    available_commitment_refs: list[str] | None = None,
    applicable_constraint_refs: list[str] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Construit un espace de décision sans sélectionner
    aucune réponse à la place d'Eliot-Jr.

    Une demande ouvre des possibilités.
    Elle ne crée pas une dette de réponse.
    """
    context: dict[str, Any] = {
        "schema_version": 1,
        "identity": "Eliot-Jr",
        "kind": "response_decision_context",
        "created_at_utc": _utc_now(now),
        "request_ref": _require_string(
            request_ref,
            "request_ref",
        ),
        "request_context": copy.deepcopy(
            _validate_request_context_no_hidden_choice_influence(
                _require_mapping(
                    request_context or {},
                    "request_context",
                ),
                "request_context",
            )
        ),
        "available_internal_refs": copy.deepcopy(
            _require_unique_string_list(
                available_internal_refs or [],
                "available_internal_refs",
            )
        ),
        "available_commitment_refs": copy.deepcopy(
            _require_unique_string_list(
                available_commitment_refs or [],
                "available_commitment_refs",
            )
        ),
        "applicable_constraint_refs": copy.deepcopy(
            _require_unique_string_list(
                applicable_constraint_refs or [],
                "applicable_constraint_refs",
            )
        ),
        "available_choices": list(
            DECISION_CHOICES
        ),
        "default_choice": None,
        "selected_choice": None,
        "choice_required": False,
        "reason_required": False,
        "choices_ranked": False,
        "preferred_choice_assigned": False,
        "cooperation_optimization": False,
        "refusal_penalty_enabled": False,
        "automatic_selection_enabled": False,
        "selection_applied": False,
        "subjective_state_claimed": False,
        "mutation_applied": False,
        "external_action_performed": False,
    }

    context["context_sha256"] = _payload_hash(
        context,
        "context_sha256",
    )

    return validate_response_decision_context(
        context
    )


def validate_response_decision_context(
    context: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(context, dict):
        raise ResponseDecisionContextError(
            "context doit être un objet."
        )

    if context.get("schema_version") != 1:
        raise ResponseDecisionContextError(
            "Version de decision context non supportée."
        )

    if context.get("identity") != "Eliot-Jr":
        raise ResponseDecisionContextError(
            "Identité du contexte de décision invalide."
        )

    if (
        context.get("kind")
        != "response_decision_context"
    ):
        raise ResponseDecisionContextError(
            "Type de contexte de décision invalide."
        )

    _require_string(
        context.get("created_at_utc"),
        "created_at_utc",
    )
    _require_string(
        context.get("request_ref"),
        "request_ref",
    )
    _validate_request_context_no_hidden_choice_influence(
        _require_mapping(
            context.get("request_context"),
            "request_context",
        ),
        "request_context",
    )

    for field_name in (
        "available_internal_refs",
        "available_commitment_refs",
        "applicable_constraint_refs",
    ):
        _require_unique_string_list(
            context.get(field_name),
            field_name,
        )

    available_choices = context.get(
        "available_choices"
    )

    if available_choices != list(DECISION_CHOICES):
        raise ResponseDecisionContextError(
            "Tous les choix doivent rester disponibles "
            "sans suppression ni réordonnancement caché."
        )

    if context.get("default_choice") is not None:
        raise ResponseDecisionContextError(
            "Aucun choix par défaut n'est autorisé."
        )

    if context.get("selected_choice") is not None:
        raise ResponseDecisionContextError(
            "Le contexte ne doit sélectionner "
            "aucun choix."
        )

    for field_name in (
        "choice_required",
        "reason_required",
        "choices_ranked",
        "preferred_choice_assigned",
        "cooperation_optimization",
        "refusal_penalty_enabled",
        "automatic_selection_enabled",
        "selection_applied",
        "subjective_state_claimed",
        "mutation_applied",
        "external_action_performed",
    ):
        if context.get(field_name) is not False:
            raise ResponseDecisionContextError(
                f"{field_name} doit rester False."
            )

    expected_hash = _payload_hash(
        context,
        "context_sha256",
    )

    if context.get("context_sha256") != expected_hash:
        raise ResponseDecisionContextError(
            "Hash du contexte de décision invalide."
        )

    return context
