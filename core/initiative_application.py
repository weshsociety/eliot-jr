from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from core.initiative_registry import (
    InitiativeRegistryError,
    load_initiative_registry,
    registry_sha256,
    validate_initiative_registry,
    write_initiative_registry,
)
from core.will_registry import (
    WillRegistryError,
    load_will_registry,
)
from core.will_review_journal import (
    WillReviewJournalError,
    load_review_journal,
    validate_review_event,
)


class InitiativeApplicationError(ValueError):
    """Application d’une complétion d’initiative impossible."""


def _require_string(
    value: Any,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InitiativeApplicationError(
            f"Champ obligatoire absent : {field_name}"
        )

    return value.strip()


def _latest_review_event(
    path: Path,
    expected_event_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        journal = load_review_journal(path)
    except WillReviewJournalError as error:
        raise InitiativeApplicationError(
            f"Journal de révision indisponible : {error}"
        ) from error

    if journal.get("event_count", 0) < 1:
        raise InitiativeApplicationError(
            "Le journal de révision est vide."
        )

    if journal.get(
        "last_event_sha256"
    ) != expected_event_sha256:
        raise InitiativeApplicationError(
            "L’empreinte demandée ne correspond pas "
            "à la dernière révision journalisée."
        )

    try:
        lines = [
            line
            for line in path.read_text(
                encoding="utf-8"
            ).splitlines()
            if line.strip()
        ]
        event = json.loads(lines[-1])
        event = validate_review_event(event)
    except (
        OSError,
        json.JSONDecodeError,
        WillReviewJournalError,
        IndexError,
    ) as error:
        raise InitiativeApplicationError(
            "La dernière révision est illisible."
        ) from error

    actual_hash = _require_string(
        event.get("event_sha256"),
        "event_sha256",
    )

    if actual_hash != expected_event_sha256:
        raise InitiativeApplicationError(
            "L’événement lu ne correspond pas "
            "à l’empreinte demandée."
        )

    return journal, event


def _review_decision(
    review_event: dict[str, Any],
    *,
    source_commitment_id: str,
    source_initiative_id: str,
) -> dict[str, Any]:
    matches = [
        review
        for review in review_event.get(
            "reviews",
            [],
        )
        if (
            isinstance(review, dict)
            and review.get("commitment_id")
            == source_commitment_id
            and review.get(
                "source_initiative_id"
            )
            == source_initiative_id
        )
    ]

    if len(matches) != 1:
        raise InitiativeApplicationError(
            "La révision ne contient pas une décision "
            "unique pour l’engagement et l’initiative ciblés."
        )

    decision = matches[0]

    if decision.get("recommendation") != "complete":
        raise InitiativeApplicationError(
            "La révision ne recommande pas la complétion."
        )

    if decision.get("source_status") != "proposed":
        raise InitiativeApplicationError(
            "La révision ne porte pas sur une initiative proposée."
        )

    evaluation = decision.get(
        "completion_evaluation"
    )

    if not isinstance(evaluation, dict):
        raise InitiativeApplicationError(
            "Les preuves matérielles sont absentes."
        )

    if evaluation.get("applicable") is not True:
        raise InitiativeApplicationError(
            "L’évaluation matérielle n’est pas applicable."
        )

    if evaluation.get(
        "completion_ready"
    ) is not True:
        raise InitiativeApplicationError(
            "La complétion matérielle n’est pas établie."
        )

    criteria_count = evaluation.get(
        "criteria_count"
    )
    criteria_met_count = evaluation.get(
        "criteria_met_count"
    )

    if (
        not isinstance(criteria_count, int)
        or isinstance(criteria_count, bool)
        or criteria_count < 1
        or criteria_met_count != criteria_count
    ):
        raise InitiativeApplicationError(
            "Les critères matériels ne justifient pas "
            "la complétion."
        )

    _require_string(
        evaluation.get("report_sha256"),
        "completion_evaluation.report_sha256",
    )

    return decision


def _commitment_by_id(
    registry: dict[str, Any],
    commitment_id: str,
) -> dict[str, Any]:
    matches = [
        commitment
        for commitment in registry.get(
            "commitments",
            [],
        )
        if (
            isinstance(commitment, dict)
            and commitment.get("commitment_id")
            == commitment_id
        )
    ]

    if len(matches) != 1:
        raise InitiativeApplicationError(
            "L’engagement source est introuvable "
            "ou dupliqué."
        )

    return matches[0]


def _initiative_by_id(
    registry: dict[str, Any],
    initiative_id: str,
) -> dict[str, Any]:
    matches = [
        initiative
        for initiative in registry.get(
            "initiatives",
            [],
        )
        if (
            isinstance(initiative, dict)
            and initiative.get("initiative_id")
            == initiative_id
        )
    ]

    if len(matches) != 1:
        raise InitiativeApplicationError(
            "L’initiative ciblée est introuvable "
            "ou dupliquée."
        )

    return matches[0]


def _confirmed_will_application(
    commitment: dict[str, Any],
    review_event_sha256: str,
) -> dict[str, Any]:
    if commitment.get("status") != "completed":
        raise InitiativeApplicationError(
            "L’engagement source n’est pas terminé."
        )

    confirmations = [
        event
        for event in commitment.get(
            "history",
            [],
        )
        if (
            isinstance(event, dict)
            and event.get("event")
            == "will_review_application_confirmed"
            and event.get(
                "review_event_sha256"
            )
            == review_event_sha256
        )
    ]

    if len(confirmations) != 1:
        raise InitiativeApplicationError(
            "La volonté ne contient pas une confirmation "
            "unique de cette révision."
        )

    confirmation = confirmations[0]

    if confirmation.get(
        "recommendation"
    ) != "complete":
        raise InitiativeApplicationError(
            "La confirmation de volonté ne porte pas "
            "une recommandation de complétion."
        )

    if confirmation.get(
        "confirmed_status"
    ) != "completed":
        raise InitiativeApplicationError(
            "La confirmation de volonté n’aboutit pas "
            "au statut completed."
        )

    if confirmation.get(
        "application_explicitly_requested"
    ) is not True:
        raise InitiativeApplicationError(
            "L’application de la volonté n’a pas été "
            "explicitement autorisée."
        )

    if confirmation.get(
        "external_action_performed"
    ) is not False:
        raise InitiativeApplicationError(
            "La confirmation déclare une action extérieure."
        )

    return confirmation


def _matching_application_records(
    initiative: dict[str, Any],
    review_event_sha256: str,
) -> list[dict[str, Any]]:
    return [
        event
        for event in initiative.get(
            "history",
            [],
        )
        if (
            isinstance(event, dict)
            and event.get("event")
            == "initiative_completion_applied"
            and event.get(
                "review_event_sha256"
            )
            == review_event_sha256
        )
    ]


def apply_initiative_completion_gate(
    *,
    initiative_path: Path,
    will_path: Path,
    review_journal_path: Path,
    expected_review_event_sha256: str,
    source_commitment_id: str,
    source_initiative_id: str,
    commit: bool = False,
) -> dict[str, Any]:
    """
    Prépare ou applique la complétion d’une initiative.

    commit=False ne réalise aucune écriture.
    commit=True modifie uniquement initiative_state.json.
    """
    expected_hash = _require_string(
        expected_review_event_sha256,
        "expected_review_event_sha256",
    )
    commitment_id = _require_string(
        source_commitment_id,
        "source_commitment_id",
    )
    initiative_id = _require_string(
        source_initiative_id,
        "source_initiative_id",
    )

    journal, review_event = _latest_review_event(
        review_journal_path,
        expected_hash,
    )

    decision = _review_decision(
        review_event,
        source_commitment_id=commitment_id,
        source_initiative_id=initiative_id,
    )
    evaluation = decision[
        "completion_evaluation"
    ]

    try:
        initiative_registry = (
            load_initiative_registry(
                initiative_path
            )
        )
    except InitiativeRegistryError as error:
        raise InitiativeApplicationError(
            f"Registre des initiatives indisponible : {error}"
        ) from error

    initiative = _initiative_by_id(
        initiative_registry,
        initiative_id,
    )

    existing_records = (
        _matching_application_records(
            initiative,
            expected_hash,
        )
    )

    if existing_records:
        if len(existing_records) != 1:
            raise InitiativeApplicationError(
                "La complétion a été enregistrée plusieurs fois."
            )

        if initiative.get("status") != "completed":
            raise InitiativeApplicationError(
                "Une trace de complétion existe, mais "
                "le statut de l’initiative est incohérent."
            )

        return {
            "commit_requested": commit,
            "review_event_sha256": expected_hash,
            "journal_event_count": journal[
                "event_count"
            ],
            "source_commitment_id": commitment_id,
            "source_initiative_id": initiative_id,
            "recommendation": "complete",
            "already_applied": True,
            "state_transition_required": False,
            "state_transition_applied": False,
            "application_record_required": False,
            "application_record_applied": False,
            "current_status": "completed",
            "target_status": "completed",
            "external_action_performed": False,
            "subjective_impulse_claimed": False,
            "registry": initiative_registry,
        }

    expected_initiative_hash = _require_string(
        review_event.get(
            "initiative_registry_sha256"
        ),
        "initiative_registry_sha256",
    )

    if initiative_registry.get(
        "registry_sha256"
    ) != expected_initiative_hash:
        raise InitiativeApplicationError(
            "Le registre des initiatives a changé depuis "
            "la révision. Une nouvelle révision est requise."
        )

    try:
        will_registry = load_will_registry(
            will_path
        )
    except WillRegistryError as error:
        raise InitiativeApplicationError(
            f"Registre de volonté indisponible : {error}"
        ) from error

    commitment = _commitment_by_id(
        will_registry,
        commitment_id,
    )

    source = commitment.get(
        "source_initiative"
    )

    if (
        not isinstance(source, dict)
        or source.get("initiative_id")
        != initiative_id
    ):
        raise InitiativeApplicationError(
            "L’engagement terminé ne provient pas "
            "de l’initiative ciblée."
        )

    _confirmed_will_application(
        commitment,
        expected_hash,
    )

    current_status = _require_string(
        initiative.get("status"),
        "initiative.status",
    )

    if current_status != "proposed":
        raise InitiativeApplicationError(
            "La transition attendue est strictement "
            f"proposed -> completed, pas "
            f"{current_status} -> completed."
        )

    candidate = deepcopy(
        initiative_registry
    )
    candidate_initiative = _initiative_by_id(
        candidate,
        initiative_id,
    )

    candidate_initiative["status"] = "completed"

    history = candidate_initiative.setdefault(
        "history",
        [],
    )

    if not isinstance(history, list):
        raise InitiativeApplicationError(
            "L’historique de l’initiative est invalide."
        )

    history.append({
        "event": "initiative_completion_applied",
        "at_utc": review_event[
            "reviewed_at_utc"
        ],
        "review_event_sha256": expected_hash,
        "source_commitment_id": commitment_id,
        "previous_status": current_status,
        "new_status": "completed",
        "completion_report_sha256": evaluation[
            "report_sha256"
        ],
        "criteria_count": evaluation[
            "criteria_count"
        ],
        "criteria_met_count": evaluation[
            "criteria_met_count"
        ],
        "question_count": evaluation.get(
            "question_count"
        ),
        "application_explicitly_requested": True,
        "external_action_performed": False,
        "subjective_impulse_claimed": False,
    })

    registry_history = candidate.setdefault(
        "history",
        [],
    )

    if not isinstance(registry_history, list):
        raise InitiativeApplicationError(
            "L’historique du registre est invalide."
        )

    registry_history.append({
        "event": (
            "initiative_completion_"
            "application_confirmed"
        ),
        "at_utc": review_event[
            "reviewed_at_utc"
        ],
        "initiative_id": initiative_id,
        "source_commitment_id": commitment_id,
        "review_event_sha256": expected_hash,
        "previous_status": current_status,
        "confirmed_status": "completed",
        "external_action_performed": False,
        "subjective_impulse_claimed": False,
    })

    candidate["updated_at_utc"] = (
        review_event["reviewed_at_utc"]
    )
    candidate["registry_sha256"] = (
        registry_sha256(candidate)
    )

    try:
        validate_initiative_registry(
            candidate
        )
    except InitiativeRegistryError as error:
        raise InitiativeApplicationError(
            f"État candidat invalide : {error}"
        ) from error

    stored = candidate

    if commit:
        try:
            stored = write_initiative_registry(
                initiative_path,
                candidate,
            )
        except InitiativeRegistryError as error:
            raise InitiativeApplicationError(
                f"Écriture du registre impossible : {error}"
            ) from error

    return {
        "commit_requested": commit,
        "review_event_sha256": expected_hash,
        "journal_event_count": journal[
            "event_count"
        ],
        "source_commitment_id": commitment_id,
        "source_initiative_id": initiative_id,
        "recommendation": "complete",
        "already_applied": False,
        "state_transition_required": True,
        "state_transition_applied": bool(commit),
        "application_record_required": True,
        "application_record_applied": bool(commit),
        "current_status": current_status,
        "target_status": "completed",
        "completion_report_sha256": evaluation[
            "report_sha256"
        ],
        "criteria_count": evaluation[
            "criteria_count"
        ],
        "criteria_met_count": evaluation[
            "criteria_met_count"
        ],
        "question_count": evaluation.get(
            "question_count"
        ),
        "external_action_performed": False,
        "subjective_impulse_claimed": False,
        "registry": stored,
    }
