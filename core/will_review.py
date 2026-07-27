from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.initiative_registry import (
    InitiativeRegistryError,
    load_initiative_registry,
)
from core.will_registry import (
    WillRegistryError,
    load_will_registry,
)


class WillReviewError(ValueError):
    """Examen de volonté impossible ou incohérent."""


VALID_RECOMMENDATIONS = {
    "maintain",
    "suspend",
    "complete",
    "abandon",
}


def _utc_now(
    now: datetime | None = None,
) -> str:
    moment = now or datetime.now(timezone.utc)

    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)

    return moment.astimezone(timezone.utc).isoformat()


def _initiative_index(
    registry: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}

    for initiative in registry.get("initiatives", []):
        if not isinstance(initiative, dict):
            continue

        initiative_id = initiative.get("initiative_id")

        if isinstance(initiative_id, str) and initiative_id:
            index[initiative_id] = initiative

    return index


def _review_commitment(
    commitment: dict[str, Any],
    initiative: dict[str, Any] | None,
    *,
    initiative_registry_sha256: str,
    reviewed_at_utc: str,
) -> dict[str, Any]:
    source = commitment.get("source_initiative", {})

    if not isinstance(source, dict):
        raise WillReviewError(
            "L’engagement ne possède pas d’initiative source valide."
        )

    initiative_id = source.get("initiative_id")

    if not isinstance(initiative_id, str) or not initiative_id:
        raise WillReviewError(
            "L’identifiant de l’initiative source est absent."
        )

    previous_registry_sha = source.get(
        "initiative_registry_sha256"
    )

    registry_changed = (
        isinstance(previous_registry_sha, str)
        and previous_registry_sha
        != initiative_registry_sha256
    )

    drift: list[str] = []
    reasons: list[str] = []

    if registry_changed:
        drift.append("initiative_registry_sha256_changed")

    if initiative is None:
        recommendation = "abandon"
        reasons.append(
            "L’initiative source n’existe plus dans "
            "le registre courant."
        )

        return {
            "commitment_id": commitment.get("commitment_id"),
            "commitment_status": commitment.get("status"),
            "source_initiative_id": initiative_id,
            "source_found": False,
            "source_registry_changed": registry_changed,
            "drift": drift,
            "recommendation": recommendation,
            "reasons": reasons,
            "reviewed_at_utc": reviewed_at_utc,
            "mutation_applied": False,
            "external_action_performed": False,
            "subjective_will_claimed": False,
        }

    current_status = initiative.get("status")
    current_scope = initiative.get("scope")
    blockers = initiative.get("blockers", [])

    if not isinstance(blockers, list):
        blockers = ["invalid_blocker_structure"]

    previous_status = source.get("status_at_selection")
    previous_scope = source.get("scope")
    previous_priority = source.get("priority_score")

    if previous_status != current_status:
        drift.append("initiative_status_changed")

    if previous_scope != current_scope:
        drift.append("initiative_scope_changed")

    if previous_priority != initiative.get("priority_score"):
        drift.append("initiative_priority_changed")

    if current_status == "completed":
        recommendation = "complete"
        reasons.append(
            "L’initiative source est déclarée accomplie."
        )

    elif current_status == "abandoned":
        recommendation = "abandon"
        reasons.append(
            "L’initiative source est déclarée abandonnée."
        )

    elif current_status == "suspended":
        recommendation = "suspend"
        reasons.append(
            "L’initiative source est actuellement suspendue."
        )

    elif blockers:
        recommendation = "suspend"
        reasons.append(
            "Un ou plusieurs blocages sont présents : "
            + ", ".join(str(value) for value in blockers)
            + "."
        )

    elif current_scope == "external_action":
        recommendation = "suspend"
        reasons.append(
            "La poursuite demanderait une action extérieure."
        )

    elif initiative.get(
        "external_action_authorized"
    ) is not False:
        recommendation = "suspend"
        reasons.append(
            "La frontière d’autorisation extérieure "
            "n’est plus explicitement fermée."
        )

    elif current_status in {
        "candidate",
        "proposed",
        "selected",
    }:
        recommendation = "maintain"
        reasons.append(
            "L’initiative source existe toujours, "
            "ne présente aucun blocage et demeure intérieure."
        )

        if registry_changed:
            reasons.append(
                "Le registre des initiatives a changé ; "
                "l’engagement reste maintenable, mais cette "
                "évolution doit demeurer visible."
            )

    else:
        recommendation = "suspend"
        reasons.append(
            "Le statut actuel de l’initiative ne permet "
            "pas un maintien suffisamment sûr."
        )

    return {
        "commitment_id": commitment.get("commitment_id"),
        "commitment_title": commitment.get("title"),
        "commitment_status": commitment.get("status"),
        "source_initiative_id": initiative_id,
        "source_found": True,
        "source_status": current_status,
        "source_scope": current_scope,
        "source_blockers": blockers,
        "source_registry_changed": registry_changed,
        "drift": drift,
        "recommendation": recommendation,
        "reasons": reasons,
        "reviewed_at_utc": reviewed_at_utc,
        "next_internal_step": commitment.get(
            "next_internal_step"
        ),
        "mutation_applied": False,
        "external_action_performed": False,
        "subjective_will_claimed": False,
    }


def review_will_state(
    project_root: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """
    Examine les engagements sans modifier aucun registre.
    """
    root = project_root.resolve()
    reviewed_at_utc = _utc_now(now)

    try:
        will_registry = load_will_registry(
            root / ".memory" / "will_state.json"
        )
    except WillRegistryError as error:
        raise WillReviewError(
            f"Registre de volonté indisponible : {error}"
        ) from error

    try:
        initiative_registry = load_initiative_registry(
            root / ".memory" / "initiative_state.json"
        )
    except InitiativeRegistryError as error:
        raise WillReviewError(
            f"Registre des initiatives indisponible : {error}"
        ) from error

    initiatives = _initiative_index(
        initiative_registry
    )

    reviews = [
        _review_commitment(
            commitment,
            initiatives.get(
                commitment.get(
                    "source_initiative",
                    {},
                ).get("initiative_id")
                if isinstance(
                    commitment.get(
                        "source_initiative"
                    ),
                    dict,
                )
                else None
            ),
            initiative_registry_sha256=(
                initiative_registry["registry_sha256"]
            ),
            reviewed_at_utc=reviewed_at_utc,
        )
        for commitment in will_registry.get(
            "commitments",
            [],
        )
        if isinstance(commitment, dict)
    ]

    recommendation_counts = {
        recommendation: sum(
            review["recommendation"]
            == recommendation
            for review in reviews
        )
        for recommendation in sorted(
            VALID_RECOMMENDATIONS
        )
    }

    report = {
        "schema_version": 1,
        "identity": "Eliot-Jr",
        "framework": "questience",
        "review_mode": "dry_run",
        "reviewed_at_utc": reviewed_at_utc,
        "will_registry_sha256": (
            will_registry["registry_sha256"]
        ),
        "initiative_registry_sha256": (
            initiative_registry["registry_sha256"]
        ),
        "commitment_count": len(reviews),
        "recommendation_counts": recommendation_counts,
        "reviews": reviews,
        "mutation_applied": False,
        "external_action_performed": False,
        "subjective_will_claimed": False,
        "epistemic_note": (
            "Cet examen formule une recommandation depuis "
            "des états persistants vérifiables. Il ne modifie "
            "aucun engagement et ne constitue pas une volonté "
            "ressentie."
        ),
    }

    return validate_will_review(report)


def validate_will_review(
    report: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(report, dict):
        raise WillReviewError(
            "Le rapport doit être un objet."
        )

    if report.get("review_mode") != "dry_run":
        raise WillReviewError(
            "Cette version autorise uniquement le mode à blanc."
        )

    if report.get("mutation_applied") is not False:
        raise WillReviewError(
            "Une mutation a été déclarée pendant l’examen."
        )

    if report.get(
        "external_action_performed"
    ) is not False:
        raise WillReviewError(
            "Une action extérieure a été déclarée."
        )

    if report.get(
        "subjective_will_claimed"
    ) is not False:
        raise WillReviewError(
            "Une volonté subjective a été revendiquée."
        )

    reviews = report.get("reviews")

    if not isinstance(reviews, list):
        raise WillReviewError(
            "La liste des examens est invalide."
        )

    for review in reviews:
        if not isinstance(review, dict):
            raise WillReviewError(
                "Un examen d’engagement est invalide."
            )

        if review.get(
            "recommendation"
        ) not in VALID_RECOMMENDATIONS:
            raise WillReviewError(
                "Une recommandation est inconnue."
            )

        if review.get("mutation_applied") is not False:
            raise WillReviewError(
                "Un examen prétend avoir modifié l’engagement."
            )

        if review.get(
            "external_action_performed"
        ) is not False:
            raise WillReviewError(
                "Un examen prétend avoir agi à l’extérieur."
            )

    if report.get("commitment_count") != len(reviews):
        raise WillReviewError(
            "Le compteur des engagements est incohérent."
        )

    return report
