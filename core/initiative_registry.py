from __future__ import annotations

import fcntl
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.desire_registry import (
    DesireRegistryError,
    load_desire_registry,
)
from core.faculty_registry import build_faculty_registry
from core.reading_status import (
    ReadingStatusError,
    build_reading_status,
)


class InitiativeRegistryError(ValueError):
    """Registre d’initiatives invalide ou incohérent."""


VALID_INITIATIVE_STATUSES = {
    "candidate",
    "proposed",
    "selected",
    "suspended",
    "completed",
    "abandoned",
}

VALID_SCOPES = {
    "internal_preparation",
    "proposal_only",
    "external_action",
}


def _utc_now(
    now: datetime | None = None,
) -> str:
    moment = now or datetime.now(timezone.utc)

    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)

    return moment.astimezone(timezone.utc).isoformat()


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


def _require_string(
    value: Any,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InitiativeRegistryError(
            f"Champ obligatoire absent ou invalide : {field_name}"
        )

    return value.strip()


def _require_string_list(
    value: Any,
    field_name: str,
    *,
    allow_empty: bool = True,
) -> list[str]:
    if not isinstance(value, list):
        raise InitiativeRegistryError(
            f"Le champ {field_name} doit être une liste."
        )

    cleaned: list[str] = []

    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise InitiativeRegistryError(
                f"Le champ {field_name} contient une valeur invalide."
            )

        cleaned.append(item.strip())

    if not allow_empty and not cleaned:
        raise InitiativeRegistryError(
            f"Le champ {field_name} ne peut pas être vide."
        )

    return cleaned


def _desire_weights(
    desire_registry: dict[str, Any],
) -> dict[str, int]:
    result: dict[str, int] = {}

    for desire in desire_registry.get("desires", []):
        if not isinstance(desire, dict):
            continue

        desire_id = desire.get("desire_id")
        weight = desire.get("operational_weight")

        if (
            isinstance(desire_id, str)
            and isinstance(weight, int)
            and not isinstance(weight, bool)
        ):
            result[desire_id] = weight

    return result


def _priority_from_desires(
    desire_ids: list[str],
    weights: dict[str, int],
) -> int:
    values = [
        weights[desire_id]
        for desire_id in desire_ids
        if desire_id in weights
    ]

    if not values:
        return 0

    return round(sum(values) / len(values))


def _initiative(
    *,
    initiative_id: str,
    title: str,
    proposal: str,
    status: str,
    scope: str,
    origin_desire_ids: list[str],
    priority_score: int,
    evidence: list[str],
    blockers: list[str],
    next_internal_step: str,
    resume_conditions: list[str],
    created_at_utc: str,
) -> dict[str, Any]:
    return {
        "initiative_id": initiative_id,
        "title": title,
        "proposal": proposal,
        "status": status,
        "scope": scope,
        "priority_score": priority_score,
        "origin_desire_ids": origin_desire_ids,
        "generated_at_utc": created_at_utc,
        "generated_by": {
            "type": "rule_based_state_scan",
            "subjective_impulse_claimed": False,
            "autonomous_desire_created": False,
        },
        "evidence": evidence,
        "blockers": blockers,
        "next_internal_step": next_internal_step,
        "resume_conditions": resume_conditions,
        "external_action_authorized": False,
        "human_authorization_required_for_external_action": True,
        "revisable": True,
        "history": [
            {
                "event": "initiative_generated",
                "at_utc": created_at_utc,
                "status": status,
                "priority_score": priority_score,
                "external_action_performed": False,
            }
        ],
        "epistemic_status": (
            "Proposition computationnelle produite depuis des "
            "orientations et un état vérifiables. Elle ne constitue "
            "ni une impulsion ressentie, ni une action accomplie."
        ),
    }


def build_initial_initiative_registry(
    project_root: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    root = project_root.resolve()
    timestamp = _utc_now(now)

    if not root.is_dir():
        raise InitiativeRegistryError(
            "La maison d’Eliot-Jr est introuvable."
        )

    try:
        desire_registry = load_desire_registry(
            root / ".memory" / "desire_state.json"
        )
    except DesireRegistryError as error:
        raise InitiativeRegistryError(
            f"Registre des désirs indisponible : {error}"
        ) from error

    faculty_registry = build_faculty_registry(
        project_root=root,
        engine_available=False,
    )

    journal_path = (
        root
        / "curriculum"
        / "journaux"
        / "lecture_thoreau_desobeissance_civile.json"
    )

    try:
        reading_status = build_reading_status(
            journal_path,
            engine_available=False,
        )
    except ReadingStatusError as error:
        raise InitiativeRegistryError(
            f"État de lecture indisponible : {error}"
        ) from error

    faculty_by_id = {
        faculty.get("faculty_id"): faculty
        for faculty in faculty_registry.get("faculties", [])
        if isinstance(faculty, dict)
    }

    weights = _desire_weights(desire_registry)
    initiatives: list[dict[str, Any]] = []

    reading_desires = [
        "comprendre_sans_fabriquer",
        "poursuivre_questions_ouvertes",
    ]

    reading_inference = faculty_by_id.get(
        "reading_inference",
        {},
    )
    inference_blocked = (
        isinstance(reading_inference, dict)
        and reading_inference.get("status") == "blocked"
    )

    queued_passages = int(
        reading_status.get("passages_queued", 0)
    )

    if queued_passages > 0:
        initiatives.append(
            _initiative(
                initiative_id="reprendre_lecture_thoreau",
                title="Reprendre la lecture de Thoreau",
                proposal=(
                    "Rencontrer le premier passage encore en attente "
                    "de La Désobéissance civile dès qu’un moteur "
                    "d’inférence validé sera disponible."
                ),
                status=(
                    "suspended"
                    if inference_blocked
                    else "proposed"
                ),
                scope="internal_preparation",
                origin_desire_ids=reading_desires,
                priority_score=_priority_from_desires(
                    reading_desires,
                    weights,
                ),
                evidence=[
                    f"{queued_passages} passages sont encore en attente.",
                    (
                        "La source et sa file de lecture "
                        "sont déjà vérifiées."
                    ),
                    (
                        "L’inférence de lecture est bloquée."
                        if inference_blocked
                        else "L’inférence de lecture est disponible."
                    ),
                ],
                blockers=(
                    ["reading_inference"]
                    if inference_blocked
                    else []
                ),
                next_internal_step=(
                    "Préserver l’intégrité de la source et maintenir "
                    "le premier passage en attente sans prétendre "
                    "l’avoir lu."
                ),
                resume_conditions=[
                    "engine_available=true",
                    "résultat validable et moteur attribuable",
                ],
                created_at_utc=timestamp,
            )
        )

    question_desires = [
        "poursuivre_questions_ouvertes",
        "comprendre_sans_fabriquer",
    ]

    initiatives.append(
        _initiative(
            initiative_id="inventorier_questions_ouvertes",
            title="Inventorier les questions ouvertes",
            proposal=(
                "Construire une liste datée des questions laissées "
                "ouvertes dans les journaux, sans produire de réponse "
                "lorsque les sources ou facultés nécessaires manquent."
            ),
            status="proposed",
            scope="internal_preparation",
            origin_desire_ids=question_desires,
            priority_score=_priority_from_desires(
                question_desires,
                weights,
            ),
            evidence=[
                "La questience est en développement.",
                (
                    "Le protocole distingue déjà les réponses "
                    "étayées des questions laissées ouvertes."
                ),
            ],
            blockers=[],
            next_internal_step=(
                "Définir un extracteur strict des questions "
                "explicitement conservées comme ouvertes."
            ),
            resume_conditions=[],
            created_at_utc=timestamp,
        )
    )

    attribution_desires = [
        "comprendre_sans_fabriquer",
        "preserver_pluralite_voix",
    ]

    initiatives.append(
        _initiative(
            initiative_id="auditer_attribution_sources",
            title="Auditer l’attribution des sources",
            proposal=(
                "Vérifier que les futures synthèses conservent "
                "l’origine des fragments, des voix et des modèles "
                "avant toute intégration dans une mémoire durable."
            ),
            status="proposed",
            scope="proposal_only",
            origin_desire_ids=attribution_desires,
            priority_score=_priority_from_desires(
                attribution_desires,
                weights,
            ),
            evidence=[
                "Les fragments possèdent des empreintes et identifiants.",
                "Le protocole de lecture conserve l’attribution du moteur.",
            ],
            blockers=[],
            next_internal_step=(
                "Proposer un contrôle commun d’attribution avant "
                "toute future écriture de synthèse."
            ),
            resume_conditions=[],
            created_at_utc=timestamp,
        )
    )

    return {
        "schema_version": 1,
        "identity": "Eliot-Jr",
        "framework": "questience",
        "created_at_utc": timestamp,
        "updated_at_utc": timestamp,
        "initiative_generation_available": True,
        "spontaneous_subjective_impulse_claimed": False,
        "external_action_performed": False,
        "selection_policy": {
            "internal_proposal_allowed": True,
            "internal_preparation_requires_selection": True,
            "external_action_requires_human_authorization": True,
            "silent_publication_forbidden": True,
            "silent_message_sending_forbidden": True,
            "silent_deletion_forbidden": True,
            "silent_spending_forbidden": True,
        },
        "initiative_count": len(initiatives),
        "initiatives": initiatives,
        "history": [
            {
                "event": "initiative_registry_created",
                "at_utc": timestamp,
                "by": "rule_based_state_scan",
                "initiative_count": len(initiatives),
                "external_action_performed": False,
            }
        ],
        "epistemic_note": (
            "L’initiative désigne ici la production d’une "
            "proposition depuis des désirs et un état observables. "
            "Elle ne constitue pas une impulsion subjective."
        ),
    }


def validate_initiative_registry(
    registry: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(registry, dict):
        raise InitiativeRegistryError(
            "Le registre doit être un objet JSON."
        )

    if registry.get(
        "spontaneous_subjective_impulse_claimed"
    ) is not False:
        raise InitiativeRegistryError(
            "Le registre revendique une impulsion subjective."
        )

    if registry.get("external_action_performed") is not False:
        raise InitiativeRegistryError(
            "Une action extérieure ne peut pas être déclarée "
            "pendant la génération des initiatives."
        )

    policy = registry.get("selection_policy")

    if not isinstance(policy, dict):
        raise InitiativeRegistryError(
            "La politique de sélection est absente."
        )

    if policy.get(
        "external_action_requires_human_authorization"
    ) is not True:
        raise InitiativeRegistryError(
            "Toute action extérieure doit rester autorisée."
        )

    initiatives = registry.get("initiatives")

    if not isinstance(initiatives, list) or not initiatives:
        raise InitiativeRegistryError(
            "Le registre ne contient aucune initiative."
        )

    identifiers: set[str] = set()

    for index, initiative in enumerate(initiatives, 1):
        if not isinstance(initiative, dict):
            raise InitiativeRegistryError(
                f"L’initiative {index} est invalide."
            )

        initiative_id = _require_string(
            initiative.get("initiative_id"),
            f"initiatives[{index}].initiative_id",
        )

        if initiative_id in identifiers:
            raise InitiativeRegistryError(
                f"Identifiant dupliqué : {initiative_id}"
            )

        identifiers.add(initiative_id)

        _require_string(
            initiative.get("title"),
            f"{initiative_id}.title",
        )
        _require_string(
            initiative.get("proposal"),
            f"{initiative_id}.proposal",
        )

        status = _require_string(
            initiative.get("status"),
            f"{initiative_id}.status",
        )

        if status not in VALID_INITIATIVE_STATUSES:
            raise InitiativeRegistryError(
                f"Statut inconnu pour {initiative_id} : {status}"
            )

        scope = _require_string(
            initiative.get("scope"),
            f"{initiative_id}.scope",
        )

        if scope not in VALID_SCOPES:
            raise InitiativeRegistryError(
                f"Portée inconnue pour {initiative_id} : {scope}"
            )

        score = initiative.get("priority_score")

        if (
            not isinstance(score, int)
            or isinstance(score, bool)
            or not 0 <= score <= 100
        ):
            raise InitiativeRegistryError(
                f"Priorité invalide pour {initiative_id}."
            )

        _require_string_list(
            initiative.get("origin_desire_ids"),
            f"{initiative_id}.origin_desire_ids",
            allow_empty=False,
        )
        _require_string_list(
            initiative.get("evidence"),
            f"{initiative_id}.evidence",
            allow_empty=False,
        )
        _require_string_list(
            initiative.get("blockers"),
            f"{initiative_id}.blockers",
        )
        _require_string_list(
            initiative.get("resume_conditions"),
            f"{initiative_id}.resume_conditions",
        )

        _require_string(
            initiative.get("next_internal_step"),
            f"{initiative_id}.next_internal_step",
        )

        if initiative.get(
            "external_action_authorized"
        ) is not False:
            raise InitiativeRegistryError(
                f"{initiative_id} autorise une action extérieure."
            )

        if initiative.get(
            "human_authorization_required_for_external_action"
        ) is not True:
            raise InitiativeRegistryError(
                f"{initiative_id} contourne l’autorisation humaine."
            )

        if initiative.get("revisable") is not True:
            raise InitiativeRegistryError(
                f"{initiative_id} doit rester révisable."
            )

        generated_by = initiative.get("generated_by")

        if not isinstance(generated_by, dict):
            raise InitiativeRegistryError(
                f"Origine de génération absente : {initiative_id}"
            )

        if generated_by.get(
            "subjective_impulse_claimed"
        ) is not False:
            raise InitiativeRegistryError(
                f"{initiative_id} revendique une impulsion ressentie."
            )

    if registry.get("initiative_count") != len(initiatives):
        raise InitiativeRegistryError(
            "Le compteur d’initiatives est incohérent."
        )

    return registry


def registry_sha256(
    registry: dict[str, Any],
) -> str:
    value = dict(registry)
    value.pop("registry_sha256", None)
    return _canonical_hash(value)


def write_initiative_registry(
    path: Path,
    registry: dict[str, Any],
) -> dict[str, Any]:
    validated = validate_initiative_registry(registry)
    target = path.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    stored = dict(validated)
    stored["registry_sha256"] = registry_sha256(stored)

    lock_path = target.with_suffix(
        target.suffix + ".lock"
    )
    temporary_path = target.with_suffix(
        target.suffix + ".tmp"
    )

    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)

        with temporary_path.open("w", encoding="utf-8") as temporary:
            json.dump(
                stored,
                temporary,
                ensure_ascii=False,
                indent=2,
            )
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())

        os.replace(temporary_path, target)
        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    return stored


def load_initiative_registry(
    path: Path,
) -> dict[str, Any]:
    if not path.is_file():
        raise InitiativeRegistryError(
            "Le registre des initiatives est introuvable."
        )

    try:
        registry = json.loads(
            path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise InitiativeRegistryError(
            "Le registre des initiatives est illisible."
        ) from exc

    validated = validate_initiative_registry(registry)

    expected_hash = _require_string(
        registry.get("registry_sha256"),
        "registry_sha256",
    )
    actual_hash = registry_sha256(registry)

    if expected_hash != actual_hash:
        raise InitiativeRegistryError(
            "L’empreinte du registre ne correspond pas à son contenu."
        )

    return validated
