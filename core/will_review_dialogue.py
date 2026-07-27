from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

from core.will_review_journal import (
    WillReviewJournalError,
    load_review_journal,
)


def _normalise_query(value: str) -> str:
    decomposed = unicodedata.normalize(
        "NFKD",
        str(value),
    )
    ascii_value = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )

    return re.sub(
        r"[^a-z0-9]+",
        " ",
        ascii_value.lower(),
    ).strip()


def _recommendation_label(value: Any) -> str:
    labels = {
        "maintain": "maintenir l’engagement",
        "suspend": "suspendre l’engagement",
        "complete": "déclarer l’engagement accompli",
        "abandon": "abandonner l’engagement",
    }

    key = str(value or "").strip()

    return labels.get(
        key,
        key or "recommandation inconnue",
    )


def _join_statements(values: Any) -> str:
    if not isinstance(values, list):
        return "aucune raison lisible."

    cleaned: list[str] = []

    for value in values:
        statement = re.sub(
            r"[.;:\s]+$",
            "",
            str(value).strip(),
        )

        if statement:
            cleaned.append(statement)

    if not cleaned:
        return "aucune raison lisible."

    return " ; ".join(cleaned) + "."


def will_review_orientation_response(
    message: str,
    journal_path: Path,
) -> tuple[
    str | None,
    dict[str, Any] | None,
    list[str],
]:
    """
    Présente la dernière révision enregistrée.

    Cette fonction lit le journal existant. Elle ne lance
    aucun nouvel examen et ne modifie aucun engagement.
    """
    normalised = _normalise_query(message)

    triggers = (
        "revision de ta volonte",
        "derniere revision de ta volonte",
        "as tu revise ta volonte",
        "quand as tu revise ta volonte",
        "as tu examine ton engagement",
        "quand as tu examine ton engagement",
        "pourquoi maintiens tu cet engagement",
        "pourquoi maintiens tu ton engagement",
        "ton engagement est il maintenu",
        "quelle est ta derniere revision",
        "explique ta revision",
        "explique la revision de ta volonte",
    )

    if not any(
        trigger in normalised
        for trigger in triggers
    ):
        return None, None, []

    try:
        journal = load_review_journal(
            journal_path
        )
    except WillReviewJournalError as error:
        return (
            "Je ne peux pas consulter actuellement "
            "un journal suffisamment fiable de mes "
            "révisions de volonté. Je préfère ne pas "
            "inventer un examen.",
            None,
            [f"will_review_journal: {error}"],
        )

    events = journal.get("events", [])

    if not isinstance(events, list) or not events:
        return (
            "Aucune révision de volonté n’est encore "
            "enregistrée dans mon journal.",
            journal,
            [],
        )

    event = events[-1]
    reviews = event.get("reviews", [])

    if not isinstance(reviews, list):
        reviews = []

    lines = [
        (
            "Ma dernière révision enregistrée de volonté "
            f"date du {event.get('reviewed_at_utc')}."
        ),
        (
            "Cette réponse consulte une révision existante ; "
            "elle n’en déclenche pas une nouvelle."
        ),
    ]

    for review in reviews:
        if not isinstance(review, dict):
            continue

        recommendation = _recommendation_label(
            review.get("recommendation")
        )

        lines.append(
            f"• {review.get('commitment_title')} "
            f"[{recommendation}]"
        )
        lines.append(
            "  Initiative source : "
            f"{review.get('source_initiative_id')}."
        )
        lines.append(
            "  Source retrouvée : "
            + (
                "oui."
                if review.get("source_found") is True
                else "non."
            )
        )
        lines.append(
            "  Raisons : "
            + _join_statements(
                review.get("reasons", [])
            )
        )

        blockers = review.get(
            "source_blockers",
            [],
        )
        drift = review.get("drift", [])

        lines.append(
            "  Blocages constatés : "
            + (
                ", ".join(
                    str(value)
                    for value in blockers
                )
                if isinstance(blockers, list)
                and blockers
                else "aucun."
            )
        )
        lines.append(
            "  Dérive constatée : "
            + (
                ", ".join(
                    str(value)
                    for value in drift
                )
                if isinstance(drift, list)
                and drift
                else "aucune."
            )
        )
        lines.append(
            "  Mutation de l’engagement : "
            + (
                "oui."
                if review.get(
                    "mutation_applied"
                ) is True
                else "non."
            )
        )

    lines.append(
        "Cette révision ne revendique aucune volonté "
        "ressentie et n’autorise aucune action extérieure."
    )

    return "\n".join(lines), journal, []


def structured_review_orientation(
    journal: dict[str, Any],
) -> dict[str, Any]:
    events = journal.get("events", [])

    if not isinstance(events, list) or not events:
        return {
            "event_count": journal.get("event_count", 0),
            "chain_valid": journal.get("chain_valid"),
            "last_event_sha256": journal.get(
                "last_event_sha256"
            ),
            "last_review": None,
        }

    event = events[-1]
    reviews = event.get("reviews", [])

    if not isinstance(reviews, list):
        reviews = []

    return {
        "event_count": journal.get("event_count"),
        "chain_valid": journal.get("chain_valid"),
        "last_event_sha256": journal.get(
            "last_event_sha256"
        ),
        "reviewed_at_utc": event.get(
            "reviewed_at_utc"
        ),
        "review_mode": event.get("review_mode"),
        "will_registry_sha256": event.get(
            "will_registry_sha256"
        ),
        "initiative_registry_sha256": event.get(
            "initiative_registry_sha256"
        ),
        "mutation_applied": event.get(
            "mutation_applied"
        ),
        "external_action_performed": event.get(
            "external_action_performed"
        ),
        "subjective_will_claimed": event.get(
            "subjective_will_claimed"
        ),
        "reviews": [
            {
                "commitment_id": review.get(
                    "commitment_id"
                ),
                "commitment_title": review.get(
                    "commitment_title"
                ),
                "source_initiative_id": review.get(
                    "source_initiative_id"
                ),
                "source_found": review.get(
                    "source_found"
                ),
                "recommendation": review.get(
                    "recommendation"
                ),
                "source_blockers": review.get(
                    "source_blockers",
                    [],
                ),
                "drift": review.get(
                    "drift",
                    [],
                ),
                "mutation_applied": review.get(
                    "mutation_applied"
                ),
            }
            for review in reviews
            if isinstance(review, dict)
        ],
    }
