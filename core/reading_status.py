from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ReadingStatusError(ValueError):
    """État de lecture absent, illisible ou incohérent."""


def _load_journal(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ReadingStatusError(
            "Le journal de lecture est introuvable."
        )

    try:
        value = json.loads(
            path.read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise ReadingStatusError(
            "Le journal de lecture est illisible."
        ) from exc

    if not isinstance(value, dict):
        raise ReadingStatusError(
            "Le journal doit contenir un objet JSON."
        )

    return value


def build_reading_status(
    journal_path: Path,
    *,
    engine_available: bool = False,
) -> dict[str, Any]:
    """
    Produit un état public minimal.

    Aucun texte, aucune réflexion et aucun chemin local
    ne sont exposés.
    """
    journal = _load_journal(journal_path)

    work = journal.get("work", {})
    queue = journal.get("reading_queue", [])
    encounters = journal.get("encounters", [])
    attempts = journal.get("inference_attempts", [])
    reading_plan = journal.get("reading_plan", {})

    if not isinstance(work, dict):
        raise ReadingStatusError(
            "La section work est invalide."
        )

    if not isinstance(queue, list):
        raise ReadingStatusError(
            "La file de lecture est invalide."
        )

    if not isinstance(encounters, list):
        raise ReadingStatusError(
            "La liste des rencontres est invalide."
        )

    if not isinstance(attempts, list):
        raise ReadingStatusError(
            "La liste des tentatives est invalide."
        )

    if not isinstance(reading_plan, dict):
        reading_plan = {}

    valid_queue_items = [
        item
        for item in queue
        if isinstance(item, dict)
    ]

    if len(valid_queue_items) != len(queue):
        raise ReadingStatusError(
            "La file contient un passage invalide."
        )

    queued_count = sum(
        item.get("status") == "queued"
        for item in valid_queue_items
    )
    encountered_count = sum(
        item.get("status") == "encountered"
        for item in valid_queue_items
    )
    provisional_reflection_count = sum(
        item.get("reflection_status")
        == "provisional_recorded"
        for item in valid_queue_items
    )

    declared_encounter_count = journal.get(
        "encounter_count",
        len(encounters),
    )

    if declared_encounter_count != len(encounters):
        raise ReadingStatusError(
            "Le compteur des rencontres est incohérent."
        )

    passage_count = len(valid_queue_items)
    known_states = queued_count + encountered_count

    return {
        "schema_version": 1,
        "journal_id": journal.get("journal_id"),
        "work": {
            "author": work.get("author"),
            "title": work.get("title"),
            "source_status": work.get("source_status"),
        },
        "journal_status": journal.get("status"),
        "reading_plan_status": reading_plan.get("status"),
        "source_sha256": work.get("source_sha256"),
        "passages_total": passage_count,
        "passages_queued": queued_count,
        "passages_encountered": encountered_count,
        "passages_other_state": passage_count - known_states,
        "encounter_count": len(encounters),
        "attempt_count": len(attempts),
        "provisional_reflection_count": (
            provisional_reflection_count
        ),
        "engine_available": bool(engine_available),
        "engine_id": None,
        "reading_complete": (
            passage_count > 0
            and encountered_count == passage_count
        ),
        "epistemic_state": (
            "Aucun passage n'est considéré comme rencontré "
            "sans résultat d'inférence validé et attribué."
        ),
    }
