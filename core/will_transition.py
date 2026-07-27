from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from core.will_review import (
    WillReviewError,
    validate_will_review,
)
from core.will_registry import (
    WillRegistryError,
    load_will_registry,
    validate_will_registry,
    write_will_registry,
)


class WillTransitionError(ValueError):
    """Transition de volonté impossible ou incohérente."""


RECOMMENDATION_TARGETS = {
    "maintain": None,
    "suspend": "suspended",
    "complete": "completed",
    "abandon": "abandoned",
}

ALLOWED_STATUS_TRANSITIONS = {
    "active": {
        "active",
        "suspended",
        "completed",
        "abandoned",
    },
    "suspended": {
        "suspended",
        "completed",
        "abandoned",
    },
    "completed": {
        "completed",
    },
    "abandoned": {
        "abandoned",
    },
}


def _require_string(
    value: Any,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WillTransitionError(
            f"Champ obligatoire absent : {field_name}"
        )

    return value.strip()


def _commitment_index(
    registry: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}

    for commitment in registry.get(
        "commitments",
        [],
    ):
        if not isinstance(commitment, dict):
            continue

        commitment_id = commitment.get(
            "commitment_id"
        )

        if (
            isinstance(commitment_id, str)
            and commitment_id
        ):
            index[commitment_id] = commitment

    return index


def build_transition_plan(
    will_registry: dict[str, Any],
    initiative_registry: dict[str, Any],
    review_report: dict[str, Any],
) -> dict[str, Any]:
    """
    Construit un plan sans modifier le registre de volonté.
    """
    try:
        validated_will = validate_will_registry(
            will_registry
        )
    except WillRegistryError as error:
        raise WillTransitionError(
            f"Registre de volonté invalide : {error}"
        ) from error

    try:
        validated_review = validate_will_review(
            review_report
        )
    except WillReviewError as error:
        raise WillTransitionError(
            f"Rapport de révision invalide : {error}"
        ) from error

    if not isinstance(initiative_registry, dict):
        raise WillTransitionError(
            "Le registre des initiatives est invalide."
        )

    will_sha = _require_string(
        validated_will.get("registry_sha256"),
        "will_registry.registry_sha256",
    )
    initiative_sha = _require_string(
        initiative_registry.get(
            "registry_sha256"
        ),
        "initiative_registry.registry_sha256",
    )

    if validated_review.get(
        "will_registry_sha256"
    ) != will_sha:
        raise WillTransitionError(
            "La révision ne correspond plus au registre "
            "de volonté courant."
        )

    if validated_review.get(
        "initiative_registry_sha256"
    ) != initiative_sha:
        raise WillTransitionError(
            "La révision ne correspond plus au registre "
            "des initiatives courant."
        )

    if validated_review.get(
        "mutation_applied"
    ) is not False:
        raise WillTransitionError(
            "La révision déclare déjà une mutation."
        )

    if validated_review.get(
        "external_action_performed"
    ) is not False:
        raise WillTransitionError(
            "La révision déclare une action extérieure."
        )

    commitments = _commitment_index(
        validated_will
    )
    decisions: list[dict[str, Any]] = []

    for review in validated_review.get(
        "reviews",
        [],
    ):
        commitment_id = _require_string(
            review.get("commitment_id"),
            "review.commitment_id",
        )

        commitment = commitments.get(
            commitment_id
        )

        if commitment is None:
            raise WillTransitionError(
                "L’engagement examiné n’existe plus : "
                f"{commitment_id}"
            )

        recommendation = _require_string(
            review.get("recommendation"),
            f"{commitment_id}.recommendation",
        )

        if recommendation not in RECOMMENDATION_TARGETS:
            raise WillTransitionError(
                f"Recommandation inconnue : {recommendation}"
            )

        current_status = _require_string(
            commitment.get("status"),
            f"{commitment_id}.status",
        )

        configured_target = (
            RECOMMENDATION_TARGETS[
                recommendation
            ]
        )

        target_status = (
            current_status
            if configured_target is None
            else configured_target
        )

        allowed_targets = (
            ALLOWED_STATUS_TRANSITIONS.get(
                current_status,
                set(),
            )
        )

        if target_status not in allowed_targets:
            raise WillTransitionError(
                "Transition interdite pour "
                f"{commitment_id} : "
                f"{current_status} -> {target_status}"
            )

        would_mutate = (
            target_status != current_status
        )

        decisions.append({
            "commitment_id": commitment_id,
            "commitment_title": (
                commitment.get("title")
            ),
            "source_initiative_id": (
                review.get(
                    "source_initiative_id"
                )
            ),
            "reviewed_at_utc": (
                validated_review[
                    "reviewed_at_utc"
                ]
            ),
            "recommendation": recommendation,
            "reasons": review.get(
                "reasons",
                [],
            ),
            "current_status": current_status,
            "target_status": target_status,
            "would_mutate": would_mutate,
            "external_action_required": False,
            "external_action_performed": False,
            "subjective_will_claimed": False,
        })

    plan = {
        "schema_version": 1,
        "identity": validated_will.get(
            "identity",
            "Eliot-Jr",
        ),
        "framework": validated_will.get(
            "framework",
            "questience",
        ),
        "mode": "transition_plan",
        "reviewed_at_utc": validated_review[
            "reviewed_at_utc"
        ],
        "will_registry_sha256": will_sha,
        "initiative_registry_sha256": (
            initiative_sha
        ),
        "decision_count": len(decisions),
        "mutation_required": any(
            decision["would_mutate"]
            for decision in decisions
        ),
        "decisions": decisions,
        "mutation_applied": False,
        "external_action_performed": False,
        "subjective_will_claimed": False,
        "epistemic_note": (
            "Ce plan traduit une recommandation validée "
            "en transition possible. Il ne modifie aucun "
            "engagement tant qu’une application explicite "
            "n’est pas demandée."
        ),
    }

    return validate_transition_plan(plan)


def validate_transition_plan(
    plan: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(plan, dict):
        raise WillTransitionError(
            "Le plan doit être un objet."
        )

    if plan.get("mode") != "transition_plan":
        raise WillTransitionError(
            "Mode de transition inconnu."
        )

    if plan.get("mutation_applied") is not False:
        raise WillTransitionError(
            "Le plan prétend déjà avoir muté un engagement."
        )

    if plan.get(
        "external_action_performed"
    ) is not False:
        raise WillTransitionError(
            "Le plan prétend avoir agi à l’extérieur."
        )

    if plan.get(
        "subjective_will_claimed"
    ) is not False:
        raise WillTransitionError(
            "Le plan revendique une volonté subjective."
        )

    _require_string(
        plan.get("will_registry_sha256"),
        "will_registry_sha256",
    )
    _require_string(
        plan.get(
            "initiative_registry_sha256"
        ),
        "initiative_registry_sha256",
    )
    _require_string(
        plan.get("reviewed_at_utc"),
        "reviewed_at_utc",
    )

    decisions = plan.get("decisions")

    if not isinstance(decisions, list):
        raise WillTransitionError(
            "La liste des décisions est invalide."
        )

    mutation_required = False

    for decision in decisions:
        if not isinstance(decision, dict):
            raise WillTransitionError(
                "Une décision est invalide."
            )

        _require_string(
            decision.get("commitment_id"),
            "decision.commitment_id",
        )

        recommendation = _require_string(
            decision.get("recommendation"),
            "decision.recommendation",
        )

        if recommendation not in RECOMMENDATION_TARGETS:
            raise WillTransitionError(
                "Une recommandation est inconnue."
            )

        current_status = _require_string(
            decision.get("current_status"),
            "decision.current_status",
        )
        target_status = _require_string(
            decision.get("target_status"),
            "decision.target_status",
        )

        if target_status not in (
            ALLOWED_STATUS_TRANSITIONS.get(
                current_status,
                set(),
            )
        ):
            raise WillTransitionError(
                "Une transition planifiée est interdite."
            )

        expected_mutation = (
            current_status != target_status
        )

        if decision.get(
            "would_mutate"
        ) is not expected_mutation:
            raise WillTransitionError(
                "L’indicateur de mutation est incohérent."
            )

        if decision.get(
            "external_action_required"
        ) is not False:
            raise WillTransitionError(
                "Une décision exige une action extérieure."
            )

        if decision.get(
            "external_action_performed"
        ) is not False:
            raise WillTransitionError(
                "Une décision déclare une action extérieure."
            )

        mutation_required = (
            mutation_required
            or expected_mutation
        )

    if plan.get("decision_count") != len(
        decisions
    ):
        raise WillTransitionError(
            "Le compteur des décisions est incohérent."
        )

    if plan.get(
        "mutation_required"
    ) is not mutation_required:
        raise WillTransitionError(
            "L’indicateur global de mutation est incohérent."
        )

    return plan


def apply_transition_plan(
    will_path: Path,
    plan: dict[str, Any],
    *,
    commit: bool = False,
) -> dict[str, Any]:
    """
    Prépare ou applique les transitions prévues.

    commit=False ne réalise aucune écriture.
    """
    validated_plan = validate_transition_plan(
        plan
    )

    try:
        current = load_will_registry(
            will_path
        )
    except WillRegistryError as error:
        raise WillTransitionError(
            f"Registre de volonté indisponible : {error}"
        ) from error

    if current.get(
        "registry_sha256"
    ) != validated_plan.get(
        "will_registry_sha256"
    ):
        raise WillTransitionError(
            "Le registre de volonté a changé depuis "
            "la construction du plan."
        )

    candidate = deepcopy(current)
    commitments = _commitment_index(candidate)
    applied_count = 0

    for decision in validated_plan["decisions"]:
        if not decision["would_mutate"]:
            continue

        commitment_id = decision[
            "commitment_id"
        ]
        commitment = commitments.get(
            commitment_id
        )

        if commitment is None:
            raise WillTransitionError(
                f"Engagement introuvable : {commitment_id}"
            )

        if commitment.get(
            "status"
        ) != decision["current_status"]:
            raise WillTransitionError(
                "Le statut de l’engagement a changé "
                "depuis la construction du plan."
            )

        commitment["status"] = decision[
            "target_status"
        ]
        commitment["last_reviewed_at_utc"] = (
            decision["reviewed_at_utc"]
        )

        history = commitment.setdefault(
            "history",
            [],
        )

        if not isinstance(history, list):
            raise WillTransitionError(
                "L’historique de l’engagement est invalide."
            )

        history.append({
            "event": "commitment_transition_applied",
            "at_utc": decision[
                "reviewed_at_utc"
            ],
            "recommendation": decision[
                "recommendation"
            ],
            "previous_status": decision[
                "current_status"
            ],
            "new_status": decision[
                "target_status"
            ],
            "reasons": decision.get(
                "reasons",
                [],
            ),
            "external_action_performed": False,
            "subjective_will_claimed": False,
        })

        applied_count += 1

    candidate["updated_at_utc"] = (
        validated_plan["reviewed_at_utc"]
    )
    candidate["active_commitment_count"] = sum(
        isinstance(commitment, dict)
        and commitment.get("status") == "active"
        for commitment in candidate.get(
            "commitments",
            [],
        )
    )

    try:
        validate_will_registry(candidate)
    except WillRegistryError as error:
        raise WillTransitionError(
            f"État candidat invalide : {error}"
        ) from error

    if commit and applied_count:
        stored = write_will_registry(
            will_path,
            candidate,
        )
    else:
        stored = candidate

    return {
        "commit_requested": commit,
        "mutation_required": (
            validated_plan[
                "mutation_required"
            ]
        ),
        "mutation_applied": bool(
            commit and applied_count
        ),
        "applied_transition_count": (
            applied_count
            if commit
            else 0
        ),
        "preview_transition_count": (
            applied_count
        ),
        "external_action_performed": False,
        "subjective_will_claimed": False,
        "registry": stored,
    }
