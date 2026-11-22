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
    candidates_root: Path | None = None,
) -> dict[str, Any]:
    """
    Produit un état public compatible avec les journaux v1 et v2.

    Les rencontres, notes externes, revues collectives et états
    d'apprentissage logique sont comptés séparément.

    Aucun texte, aucune réflexion et aucun chemin local ne sont exposés.
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

    valid_encounters = [
        item
        for item in encounters
        if isinstance(item, dict)
    ]

    if len(valid_queue_items) != len(queue):
        raise ReadingStatusError(
            "La file contient un passage invalide."
        )

    if len(valid_encounters) != len(encounters):
        raise ReadingStatusError(
            "La liste contient une rencontre invalide."
        )

    queued_count = sum(
        item.get("status") == "queued"
        for item in valid_queue_items
    )

    encountered_count = sum(
        item.get("status") == "encountered"
        for item in valid_queue_items
    )

    declared_encounter_count = journal.get(
        "encounter_count",
        len(valid_encounters),
    )

    if declared_encounter_count != len(valid_encounters):
        raise ReadingStatusError(
            "Le compteur des rencontres est incohérent."
        )

    def is_external_note(
        encounter: dict[str, Any],
    ) -> bool:
        note = encounter.get(
            "external_reading_note"
        )

        if isinstance(note, dict):
            return note.get("status") == "recorded"

        engine = encounter.get(
            "engine_attribution"
        )

        has_legacy_output = any(
            key in encounter
            for key in (
                "what_passage_says",
                "provisional_understanding",
                "questions_or_objections",
                "limits",
            )
        )

        return (
            isinstance(engine, dict)
            and bool(encounter.get("result_sha256"))
            and has_legacy_output
        )

    external_note_passages = {
        str(encounter.get("passage_id"))
        for encounter in valid_encounters
        if (
            encounter.get("passage_id")
            and is_external_note(encounter)
        )
    }

    reviewed_passages: set[str] = set()

    for encounter in valid_encounters:
        passage_id = str(
            encounter.get("passage_id", "")
        ).strip()

        review = encounter.get(
            "collective_review"
        )

        if (
            passage_id
            and isinstance(review, dict)
            and review.get("status")
            not in (
                None,
                "",
                "not_recorded",
            )
        ):
            reviewed_passages.add(passage_id)

    if candidates_root is not None:
        if not isinstance(candidates_root, Path):
            candidates_root = Path(candidates_root)

        if candidates_root.exists():
            for candidate_path in sorted(
                candidates_root.glob("*.json")
            ):
                try:
                    candidate = json.loads(
                        candidate_path.read_text(
                            encoding="utf-8"
                        )
                    )
                except (
                    OSError,
                    json.JSONDecodeError,
                ) as exc:
                    raise ReadingStatusError(
                        "Une candidate de lecture "
                        "est illisible."
                    ) from exc

                if not isinstance(candidate, dict):
                    raise ReadingStatusError(
                        "Une candidate de lecture "
                        "est invalide."
                    )

                passage_id = str(
                    candidate.get(
                        "passage_id",
                        "",
                    )
                ).strip()

                review = candidate.get(
                    "collective_review_attribution",
                    candidate.get("review", {}),
                )

                if not isinstance(review, dict):
                    continue

                decision = review.get(
                    "status",
                    review.get("decision"),
                )

                if passage_id and decision:
                    reviewed_passages.add(
                        passage_id
                    )

    logical_learning_count = 0
    logical_learning_pending_count = 0
    legacy_external_note_count = 0

    for encounter in valid_encounters:
        learning = encounter.get(
            "eliot_learning_state"
        )

        if isinstance(learning, dict):
            status = learning.get("status")

            if status == "not_yet_processed":
                logical_learning_pending_count += 1
            elif status not in (
                None,
                "",
                "not_recorded",
            ):
                logical_learning_count += 1

            continue

        if is_external_note(encounter):
            legacy_external_note_count += 1
            logical_learning_pending_count += 1

    passage_count = len(valid_queue_items)
    known_states = queued_count + encountered_count

    journal_schema_version = journal.get(
        "schema_version",
        1,
    )

    return {
        "schema_version": 2,
        "journal_schema_version": (
            journal_schema_version
        ),
        "journal_id": journal.get("journal_id"),
        "work": {
            "author": work.get("author"),
            "title": work.get("title"),
            "source_status": work.get(
                "source_status"
            ),
        },
        "journal_status": journal.get("status"),
        "reading_plan_status": reading_plan.get(
            "status"
        ),
        "source_sha256": work.get(
            "source_sha256"
        ),
        "passages_total": passage_count,
        "passages_queued": queued_count,
        "passages_encountered": (
            encountered_count
        ),
        "passages_other_state": (
            passage_count - known_states
        ),
        "encounter_count": len(
            valid_encounters
        ),
        "attempt_count": len(attempts),
        "external_reading_note_count": len(
            external_note_passages
        ),
        "collective_review_count": len(
            reviewed_passages
            & external_note_passages
        ),
        "logical_learning_count": (
            logical_learning_count
        ),
        "logical_learning_pending_count": (
            logical_learning_pending_count
        ),
        "legacy_external_note_"
        "classification_count": (
            legacy_external_note_count
        ),
        "engine_available": bool(
            engine_available
        ),
        "engine_id": None,
        "reading_complete": (
            passage_count > 0
            and encountered_count == passage_count
        ),
        "reading_complete_scope": (
            "passage_encounter_only"
        ),
        "logical_learning_complete": (
            passage_count > 0
            and logical_learning_count
            == passage_count
        ),
        "epistemic_state": (
            "Une rencontre indique qu'un passage "
            "est entré dans la chronologie. "
            "Les notes externes, les revues "
            "collectives et les apprentissages "
            "logiques sont comptés séparément."
        ),
    }
