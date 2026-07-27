from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from core.will_review import (
    WillReviewError,
    validate_will_review,
)


class WillReviewJournalError(ValueError):
    """Journal des révisions de volonté invalide."""


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(encoded).hexdigest()


def _event_sha256(
    event: dict[str, Any],
) -> str:
    value = dict(event)
    value.pop("event_sha256", None)

    return _canonical_hash(value)


def _require_string(
    value: Any,
    field_name: str,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WillReviewJournalError(
            f"Champ obligatoire absent : {field_name}"
        )

    return value.strip()


def _review_snapshot(
    review: dict[str, Any],
) -> dict[str, Any]:
    return {
        "commitment_id": review.get(
            "commitment_id"
        ),
        "commitment_title": review.get(
            "commitment_title"
        ),
        "commitment_status": review.get(
            "commitment_status"
        ),
        "source_initiative_id": review.get(
            "source_initiative_id"
        ),
        "source_found": review.get(
            "source_found"
        ),
        "source_status": review.get(
            "source_status"
        ),
        "source_scope": review.get(
            "source_scope"
        ),
        "source_blockers": review.get(
            "source_blockers",
            [],
        ),
        "source_registry_changed": review.get(
            "source_registry_changed"
        ),
        "drift": review.get("drift", []),
        "recommendation": review.get(
            "recommendation"
        ),
        "reasons": review.get("reasons", []),
        "next_internal_step": review.get(
            "next_internal_step"
        ),
        "mutation_applied": False,
        "external_action_performed": False,
        "subjective_will_claimed": False,
    }


def build_review_event(
    report: dict[str, Any],
    *,
    previous_event_sha256: str | None,
) -> dict[str, Any]:
    try:
        validated = validate_will_review(
            report
        )
    except WillReviewError as error:
        raise WillReviewJournalError(
            f"Rapport de révision invalide : {error}"
        ) from error

    event = {
        "schema_version": 1,
        "event_type": "will_review",
        "identity": validated.get(
            "identity",
            "Eliot-Jr",
        ),
        "framework": validated.get(
            "framework",
            "questience",
        ),
        "reviewed_at_utc": validated[
            "reviewed_at_utc"
        ],
        "review_mode": validated[
            "review_mode"
        ],
        "will_registry_sha256": validated[
            "will_registry_sha256"
        ],
        "initiative_registry_sha256": validated[
            "initiative_registry_sha256"
        ],
        "report_sha256": _canonical_hash(
            validated
        ),
        "previous_event_sha256": (
            previous_event_sha256
        ),
        "commitment_count": validated[
            "commitment_count"
        ],
        "recommendation_counts": validated[
            "recommendation_counts"
        ],
        "reviews": [
            _review_snapshot(review)
            for review in validated["reviews"]
        ],
        "mutation_applied": False,
        "external_action_performed": False,
        "subjective_will_claimed": False,
        "epistemic_note": (
            "Entrée chronologique d’un examen à blanc. "
            "Elle conserve la recommandation et ses raisons, "
            "sans modifier l’engagement examiné."
        ),
    }

    event["event_sha256"] = _event_sha256(
        event
    )

    return validate_review_event(event)


def validate_review_event(
    event: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(event, dict):
        raise WillReviewJournalError(
            "L’entrée doit être un objet JSON."
        )

    if event.get("schema_version") != 1:
        raise WillReviewJournalError(
            "Version de schéma inconnue."
        )

    if event.get("event_type") != "will_review":
        raise WillReviewJournalError(
            "Type d’événement inconnu."
        )

    if event.get("review_mode") != "dry_run":
        raise WillReviewJournalError(
            "Seules les révisions à blanc sont admises."
        )

    if event.get("mutation_applied") is not False:
        raise WillReviewJournalError(
            "Une mutation est déclarée."
        )

    if event.get(
        "external_action_performed"
    ) is not False:
        raise WillReviewJournalError(
            "Une action extérieure est déclarée."
        )

    if event.get(
        "subjective_will_claimed"
    ) is not False:
        raise WillReviewJournalError(
            "Une volonté subjective est revendiquée."
        )

    _require_string(
        event.get("reviewed_at_utc"),
        "reviewed_at_utc",
    )
    _require_string(
        event.get("will_registry_sha256"),
        "will_registry_sha256",
    )
    _require_string(
        event.get(
            "initiative_registry_sha256"
        ),
        "initiative_registry_sha256",
    )
    _require_string(
        event.get("report_sha256"),
        "report_sha256",
    )

    previous = event.get(
        "previous_event_sha256"
    )

    if previous is not None:
        _require_string(
            previous,
            "previous_event_sha256",
        )

    reviews = event.get("reviews")

    if not isinstance(reviews, list):
        raise WillReviewJournalError(
            "La liste des examens est invalide."
        )

    if event.get("commitment_count") != len(
        reviews
    ):
        raise WillReviewJournalError(
            "Le compteur des engagements est incohérent."
        )

    for review in reviews:
        if not isinstance(review, dict):
            raise WillReviewJournalError(
                "Un examen est invalide."
            )

        if review.get("mutation_applied") is not False:
            raise WillReviewJournalError(
                "Un examen déclare une mutation."
            )

        if review.get(
            "external_action_performed"
        ) is not False:
            raise WillReviewJournalError(
                "Un examen déclare une action extérieure."
            )

        if review.get(
            "subjective_will_claimed"
        ) is not False:
            raise WillReviewJournalError(
                "Un examen revendique une volonté subjective."
            )

    expected_hash = _require_string(
        event.get("event_sha256"),
        "event_sha256",
    )
    actual_hash = _event_sha256(event)

    if expected_hash != actual_hash:
        raise WillReviewJournalError(
            "L’empreinte de l’entrée ne correspond "
            "pas à son contenu."
        )

    return event


def _load_events_unlocked(
    path: Path,
) -> list[dict[str, Any]]:
    if not path.is_file():
        return []

    events: list[dict[str, Any]] = []
    previous_hash: str | None = None

    try:
        lines = path.read_text(
            encoding="utf-8"
        ).splitlines()
    except OSError as error:
        raise WillReviewJournalError(
            "Le journal est illisible."
        ) from error

    for line_number, line in enumerate(
        lines,
        1,
    ):
        if not line.strip():
            continue

        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise WillReviewJournalError(
                f"JSON invalide à la ligne {line_number}."
            ) from error

        validated = validate_review_event(
            event
        )

        if validated.get(
            "previous_event_sha256"
        ) != previous_hash:
            raise WillReviewJournalError(
                "Chaîne chronologique rompue à la "
                f"ligne {line_number}."
            )

        events.append(validated)
        previous_hash = validated[
            "event_sha256"
        ]

    return events


def load_review_journal(
    path: Path,
) -> dict[str, Any]:
    target = path.resolve()
    events = _load_events_unlocked(target)

    return {
        "schema_version": 1,
        "event_count": len(events),
        "events": events,
        "last_event_sha256": (
            events[-1]["event_sha256"]
            if events
            else None
        ),
        "chain_valid": True,
    }


def append_review_event(
    path: Path,
    report: dict[str, Any],
) -> dict[str, Any]:
    target = path.resolve()
    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    lock_path = target.with_suffix(
        target.suffix + ".lock"
    )
    temporary_path = target.with_suffix(
        target.suffix + ".tmp"
    )

    with lock_path.open(
        "a+",
        encoding="utf-8",
    ) as lock:
        fcntl.flock(
            lock.fileno(),
            fcntl.LOCK_EX,
        )

        events = _load_events_unlocked(
            target
        )

        previous_hash = (
            events[-1]["event_sha256"]
            if events
            else None
        )

        event = build_review_event(
            report,
            previous_event_sha256=previous_hash,
        )
        updated_events = [*events, event]

        with temporary_path.open(
            "w",
            encoding="utf-8",
        ) as temporary:
            for stored_event in updated_events:
                temporary.write(
                    json.dumps(
                        stored_event,
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )
                temporary.write("\n")

            temporary.flush()
            os.fsync(temporary.fileno())

        os.replace(
            temporary_path,
            target,
        )

        fcntl.flock(
            lock.fileno(),
            fcntl.LOCK_UN,
        )

    return {
        "event": event,
        "event_count": len(updated_events),
        "last_event_sha256": event[
            "event_sha256"
        ],
        "chain_valid": True,
    }
