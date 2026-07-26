from __future__ import annotations

import hashlib
import json
from typing import Any


class InferenceValidationError(ValueError):
    """Résultat d’inférence invalide ou insuffisamment attribuable."""


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


def _require_non_empty_string(
    value: Any,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InferenceValidationError(
            f"Champ obligatoire absent ou invalide : {field_name}"
        )

    return value.strip()


def _require_string_list(
    value: Any,
    field_name: str,
    allow_empty: bool = False,
) -> list[str]:
    if not isinstance(value, list):
        raise InferenceValidationError(
            f"Le champ {field_name} doit être une liste."
        )

    cleaned: list[str] = []

    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise InferenceValidationError(
                f"Le champ {field_name} contient une valeur invalide."
            )

        cleaned.append(item.strip())

    if not allow_empty and not cleaned:
        raise InferenceValidationError(
            f"Le champ {field_name} ne peut pas être vide."
        )

    return cleaned


def validate_inference_result(
    request: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any]:
    """
    Valide un résultat sans modifier le journal vivant.

    Une réflexion n’est recevable que si :
    - la requête et le contenu correspondent ;
    - le moteur et le modèle sont identifiés ;
    - la sortie distingue texte, compréhension, objection et limites.
    """
    if not isinstance(request, dict):
        raise InferenceValidationError(
            "La requête d’inférence est invalide."
        )

    if not isinstance(result, dict):
        raise InferenceValidationError(
            "Le résultat d’inférence est invalide."
        )

    expected_request_hash = _require_non_empty_string(
        request.get("request_sha256"),
        "request.request_sha256",
    )
    expected_payload_hash = _require_non_empty_string(
        request.get("payload_sha256"),
        "request.payload_sha256",
    )

    result_request_hash = _require_non_empty_string(
        result.get("request_sha256"),
        "result.request_sha256",
    )
    result_payload_hash = _require_non_empty_string(
        result.get("payload_sha256"),
        "result.payload_sha256",
    )

    if result_request_hash != expected_request_hash:
        raise InferenceValidationError(
            "Le résultat ne correspond pas à cette tentative."
        )

    if result_payload_hash != expected_payload_hash:
        raise InferenceValidationError(
            "Le résultat ne correspond pas au contenu transmis."
        )

    status = _require_non_empty_string(
        result.get("status"),
        "result.status",
    )

    allowed_statuses = {
        "completed",
        "engine_unavailable",
        "failed",
    }

    if status not in allowed_statuses:
        raise InferenceValidationError(
            f"Statut d’inférence inconnu : {status}"
        )

    engine_id = _require_non_empty_string(
        result.get("engine_id"),
        "result.engine_id",
    )

    completed_at = _require_non_empty_string(
        result.get("completed_at_utc"),
        "result.completed_at_utc",
    )

    reflection_produced = result.get(
        "reflection_produced"
    )

    if not isinstance(reflection_produced, bool):
        raise InferenceValidationError(
            "reflection_produced doit être un booléen."
        )

    output = result.get("output")
    model = result.get("model")

    if not reflection_produced:
        if status == "completed":
            raise InferenceValidationError(
                "Un résultat completed doit contenir une réflexion."
            )

        if output is not None:
            raise InferenceValidationError(
                "Une tentative sans réflexion doit avoir output=null."
            )

        normalized = {
            "schema_version": 1,
            "status": status,
            "engine_id": engine_id,
            "model": model,
            "payload_sha256": result_payload_hash,
            "request_sha256": result_request_hash,
            "reflection_produced": False,
            "output": None,
            "message": result.get("message"),
            "completed_at_utc": completed_at,
            "validated": True,
        }

        normalized["result_sha256"] = _canonical_hash(
            normalized
        )

        return normalized

    if status != "completed":
        raise InferenceValidationError(
            "Une réflexion ne peut être acceptée que si "
            "le statut est completed."
        )

    if not isinstance(model, dict):
        raise InferenceValidationError(
            "Le modèle doit être identifié pour toute réflexion."
        )

    provider = _require_non_empty_string(
        model.get("provider"),
        "model.provider",
    )
    model_id = _require_non_empty_string(
        model.get("model_id"),
        "model.model_id",
    )
    model_version = _require_non_empty_string(
        model.get("version"),
        "model.version",
    )

    if not isinstance(output, dict):
        raise InferenceValidationError(
            "La réflexion produite doit être un objet structuré."
        )

    passage = request.get("passage", {})

    if not isinstance(passage, dict):
        raise InferenceValidationError(
            "Le passage de la requête est invalide."
        )

    expected_passage_hash = _require_non_empty_string(
        passage.get("passage_sha256"),
        "request.passage.passage_sha256",
    )

    output_passage_hash = _require_non_empty_string(
        output.get("passage_sha256"),
        "output.passage_sha256",
    )

    if output_passage_hash != expected_passage_hash:
        raise InferenceValidationError(
            "La réflexion ne correspond pas au passage transmis."
        )

    what_passage_says = _require_non_empty_string(
        output.get("what_passage_says"),
        "output.what_passage_says",
    )
    provisional_understanding = _require_non_empty_string(
        output.get("provisional_understanding"),
        "output.provisional_understanding",
    )
    questions_or_objections = _require_string_list(
        output.get("questions_or_objections"),
        "output.questions_or_objections",
    )
    limits = _require_string_list(
        output.get("limits"),
        "output.limits",
    )

    normalized = {
        "schema_version": 1,
        "status": status,
        "engine_id": engine_id,
        "model": {
            "provider": provider,
            "model_id": model_id,
            "version": model_version,
        },
        "payload_sha256": result_payload_hash,
        "request_sha256": result_request_hash,
        "reflection_produced": True,
        "output": {
            "passage_sha256": output_passage_hash,
            "what_passage_says": what_passage_says,
            "provisional_understanding": (
                provisional_understanding
            ),
            "questions_or_objections": (
                questions_or_objections
            ),
            "limits": limits,
        },
        "message": result.get("message"),
        "completed_at_utc": completed_at,
        "validated": True,
    }

    normalized["result_sha256"] = _canonical_hash(
        normalized
    )

    return normalized
