from __future__ import annotations

from pathlib import Path
from typing import Any

from core.initiative_registry import (
    InitiativeRegistryError,
    load_initiative_registry,
)
from core.will_registry import (
    WillRegistryError,
    load_will_registry,
    validate_will_registry,
    write_will_registry,
)
from core.will_review import (
    WillReviewError,
    validate_will_review,
)
from core.will_review_journal import (
    WillReviewJournalError,
    load_review_journal,
)
from core.will_transition import (
    WillTransitionError,
    apply_transition_plan,
    build_transition_plan,
)


class WillApplicationError(ValueError):
    """Application d’une révision de volonté impossible."""


def _require_string(
    value: Any,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WillApplicationError(
            f"Champ obligatoire absent : {field_name}"
        )

    return value.strip()


def _report_from_event(
    event: dict[str, Any],
) -> dict[str, Any]:
    report = {
        "schema_version": 1,
        "identity": event.get(
            "identity",
            "Eliot-Jr",
        ),
        "framework": event.get(
            "framework",
            "questience",
        ),
        "review_mode": event.get(
            "review_mode"
        ),
        "reviewed_at_utc": event.get(
            "reviewed_at_utc"
        ),
        "will_registry_sha256": event.get(
            "will_registry_sha256"
        ),
        "initiative_registry_sha256": event.get(
            "initiative_registry_sha256"
        ),
        "commitment_count": event.get(
            "commitment_count"
        ),
        "recommendation_counts": event.get(
            "recommendation_counts"
        ),
        "reviews": event.get(
            "reviews",
            [],
        ),
        "mutation_applied": False,
        "external_action_performed": False,
        "subjective_will_claimed": False,
        "epistemic_note": (
            "Rapport reconstruit depuis une entrée "
            "chaînée du journal des révisions."
        ),
    }

    try:
        return validate_will_review(report)
    except WillReviewError as error:
        raise WillApplicationError(
            f"Révision journalisée invalide : {error}"
        ) from error


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


def _application_already_recorded(
    registry: dict[str, Any],
    review_event_sha256: str,
) -> bool:
    for commitment in registry.get(
        "commitments",
        [],
    ):
        if not isinstance(commitment, dict):
            continue

        history = commitment.get(
            "history",
            [],
        )

        if not isinstance(history, list):
            continue

        for event in history:
            if (
                isinstance(event, dict)
                and event.get(
                    "review_event_sha256"
                ) == review_event_sha256
                and event.get("event")
                == "will_review_application_confirmed"
            ):
                return True

    return False


def _latest_review_event(
    journal_path: Path,
    expected_event_sha256: str,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
]:
    try:
        journal = load_review_journal(
            journal_path
        )
    except WillReviewJournalError as error:
        raise WillApplicationError(
            f"Journal des révisions indisponible : {error}"
        ) from error

    events = journal.get("events", [])

    if not isinstance(events, list) or not events:
        raise WillApplicationError(
            "Aucune révision journalisée n’est disponible."
        )

    event = events[-1]
    actual_hash = _require_string(
        event.get("event_sha256"),
        "event_sha256",
    )

    if actual_hash != expected_event_sha256:
        raise WillApplicationError(
            "L’empreinte demandée ne correspond pas "
            "à la dernière révision journalisée."
        )

    return journal, event


def apply_review_gate(
    *,
    will_path: Path,
    initiative_path: Path,
    review_journal_path: Path,
    expected_review_event_sha256: str,
    commit: bool = False,
) -> dict[str, Any]:
    """
    Prépare ou applique explicitement la dernière révision.

    commit=False ne réalise aucune écriture.
    commit=True inscrit la décision dans will_state.json.
    """
    expected_hash = _require_string(
        expected_review_event_sha256,
        "expected_review_event_sha256",
    )

    journal, review_event = _latest_review_event(
        review_journal_path,
        expected_hash,
    )

    try:
        will_registry = load_will_registry(
            will_path
        )
    except WillRegistryError as error:
        raise WillApplicationError(
            f"Registre de volonté indisponible : {error}"
        ) from error

    if _application_already_recorded(
        will_registry,
        expected_hash,
    ):
        return {
            "commit_requested": commit,
            "review_event_sha256": expected_hash,
            "journal_event_count": journal[
                "event_count"
            ],
            "already_applied": True,
            "application_record_required": False,
            "application_record_applied": False,
            "state_transition_required": False,
            "state_transition_applied": False,
            "external_action_performed": False,
            "subjective_will_claimed": False,
            "registry": will_registry,
        }

    try:
        initiative_registry = (
            load_initiative_registry(
                initiative_path
            )
        )
    except InitiativeRegistryError as error:
        raise WillApplicationError(
            f"Registre des initiatives indisponible : {error}"
        ) from error

    if will_registry.get(
        "registry_sha256"
    ) != review_event.get(
        "will_registry_sha256"
    ):
        raise WillApplicationError(
            "Le registre de volonté a changé depuis "
            "la révision. Une nouvelle révision est requise."
        )

    if initiative_registry.get(
        "registry_sha256"
    ) != review_event.get(
        "initiative_registry_sha256"
    ):
        raise WillApplicationError(
            "Le registre des initiatives a changé depuis "
            "la révision. Une nouvelle révision est requise."
        )

    report = _report_from_event(
        review_event
    )

    try:
        plan = build_transition_plan(
            will_registry,
            initiative_registry,
            report,
        )
        preview = apply_transition_plan(
            will_path,
            plan,
            commit=False,
        )
    except WillTransitionError as error:
        raise WillApplicationError(
            f"Transition impossible : {error}"
        ) from error

    candidate = preview["registry"]
    commitments = _commitment_index(
        candidate
    )

    recorded_count = 0

    for decision in plan["decisions"]:
        commitment_id = _require_string(
            decision.get("commitment_id"),
            "decision.commitment_id",
        )

        commitment = commitments.get(
            commitment_id
        )

        if commitment is None:
            raise WillApplicationError(
                f"Engagement introuvable : {commitment_id}"
            )

        history = commitment.setdefault(
            "history",
            [],
        )

        if not isinstance(history, list):
            raise WillApplicationError(
                "L’historique de l’engagement est invalide."
            )

        history.append({
            "event": "will_review_application_confirmed",
            "at_utc": review_event[
                "reviewed_at_utc"
            ],
            "review_event_sha256": expected_hash,
            "recommendation": decision[
                "recommendation"
            ],
            "previous_status": decision[
                "current_status"
            ],
            "confirmed_status": decision[
                "target_status"
            ],
            "state_changed": decision[
                "would_mutate"
            ],
            "reasons": decision.get(
                "reasons",
                [],
            ),
            "application_explicitly_requested": True,
            "external_action_performed": False,
            "subjective_will_claimed": False,
        })

        commitment["last_reviewed_at_utc"] = (
            review_event["reviewed_at_utc"]
        )

        recorded_count += 1

    candidate["updated_at_utc"] = (
        review_event["reviewed_at_utc"]
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
        raise WillApplicationError(
            f"État candidat invalide : {error}"
        ) from error

    stored = candidate

    if commit:
        try:
            stored = write_will_registry(
                will_path,
                candidate,
            )
        except WillRegistryError as error:
            raise WillApplicationError(
                f"Écriture du registre impossible : {error}"
            ) from error

    return {
        "commit_requested": commit,
        "review_event_sha256": expected_hash,
        "journal_event_count": journal[
            "event_count"
        ],
        "already_applied": False,
        "application_record_required": (
            recorded_count > 0
        ),
        "application_record_applied": bool(
            commit and recorded_count
        ),
        "recorded_commitment_count": (
            recorded_count
            if commit
            else 0
        ),
        "preview_record_count": recorded_count,
        "state_transition_required": plan[
            "mutation_required"
        ],
        "state_transition_applied": bool(
            commit
            and plan["mutation_required"]
        ),
        "external_action_performed": False,
        "subjective_will_claimed": False,
        "plan": plan,
        "registry": stored,
    }
