from __future__ import annotations

from pathlib import Path
import hashlib
import json
import sys


ROOT = Path("/home/eliot-jr")
JOURNAL = (
    ROOT
    / "curriculum"
    / "journaux"
    / "lecture_thoreau_desobeissance_civile.json"
)

EXPECTED = {
    "passage_0001": {
        "relations": 1,
        "references": 12,
    },
    "passage_0002": {
        "relations": 1,
        "references": 0,
    },
    "passage_0003": {
        "relations": 3,
        "references": 4,
    },
    "passage_0004": {
        "relations": 1,
        "references": 5,
    },
}


def fail(message: str) -> None:
    raise AssertionError(message)


def main() -> int:
    before = JOURNAL.read_bytes()
    document = json.loads(
        before.decode("utf-8")
    )

    if document.get("schema_version") != 2:
        fail("Le journal n'est pas en schéma v2.")

    encounters_list = document.get(
        "encounters"
    )
    queue_list = document.get(
        "reading_queue"
    )

    if not isinstance(
        encounters_list,
        list,
    ):
        fail("La liste encounters est absente.")

    if not isinstance(
        queue_list,
        list,
    ):
        fail("La liste reading_queue est absente.")

    encounters = {
        item["passage_id"]: item
        for item in encounters_list
    }

    queue = {
        item["passage_id"]: item
        for item in queue_list
    }

    if len(encounters) != 4:
        fail(
            "Nombre inattendu de rencontres : "
            f"{len(encounters)}"
        )

    print(
        "===== AUDIT GLOBAL DES APPRENTISSAGES ====="
    )
    print(
        "Journal SHA-256 :",
        hashlib.sha256(
            before
        ).hexdigest(),
    )
    print(
        "Schéma du journal :",
        document["schema_version"],
    )
    print(
        "Rencontres :",
        len(encounters),
    )
    print()

    for passage_id, expected in (
        EXPECTED.items()
    ):
        encounter = encounters.get(
            passage_id
        )

        if not isinstance(
            encounter,
            dict,
        ):
            fail(
                f"Rencontre absente : {passage_id}"
            )

        state = encounter.get(
            "eliot_learning_state"
        )

        if not isinstance(
            state,
            dict,
        ):
            fail(
                "État d'apprentissage absent : "
                f"{passage_id}"
            )

        checks = {
            "status": (
                state.get("status")
                == "processed"
            ),
            "processing_mode": (
                state.get("processing_mode")
                == "deterministic_non_llm"
            ),
            "llm_used": (
                state.get("llm_used")
                is False
            ),
            "human_approval": (
                state.get(
                    "human_approval_required_to_exist"
                )
                is False
            ),
            "relations": (
                len(
                    state.get(
                        "relations",
                        [],
                    )
                )
                == expected["relations"]
            ),
            "references": (
                len(
                    state.get(
                        "reference_forms",
                        [],
                    )
                )
                == expected["references"]
            ),
            "ambiguities": (
                state.get(
                    "ambiguities"
                )
                == []
            ),
            "questions": (
                state.get(
                    "questions"
                )
                == []
            ),
            "hypotheses": (
                state.get(
                    "hypotheses"
                )
                == []
            ),
            "contradictions": (
                state.get(
                    "contradictions"
                )
                == []
            ),
            "content_sha": bool(
                state.get(
                    "learning_content_sha256"
                )
            ),
            "state_sha": bool(
                state.get(
                    "learning_state_sha256"
                )
            ),
        }

        failed = [
            key
            for key, ok in checks.items()
            if not ok
        ]

        if failed:
            fail(
                f"{passage_id} invalide : "
                + ", ".join(failed)
            )

        queue_item = queue.get(
            passage_id
        )

        if not isinstance(
            queue_item,
            dict,
        ):
            fail(
                "Entrée de file absente : "
                f"{passage_id}"
            )

        if (
            queue_item.get(
                "eliot_learning_status"
            )
            != "processed"
        ):
            fail(
                "Statut de file invalide : "
                f"{passage_id}"
            )

        print(
            passage_id,
            {
                "status": state["status"],
                "relations": len(
                    state["relations"]
                ),
                "references": len(
                    state["reference_forms"]
                ),
                "ambiguities": len(
                    state["ambiguities"]
                ),
                "questions": len(
                    state["questions"]
                ),
                "content_sha": (
                    state[
                        "learning_content_sha256"
                    ][:16]
                ),
                "state_sha": (
                    state[
                        "learning_state_sha256"
                    ][:16]
                ),
            },
        )

    passage_0005 = queue.get(
        "passage_0005"
    )

    if not isinstance(
        passage_0005,
        dict,
    ):
        fail(
            "Passage 0005 absent de la file."
        )

    if (
        passage_0005.get("status")
        != "queued"
    ):
        fail(
            "Passage 0005 n'est plus queued."
        )

    if (
        passage_0005.get(
            "eliot_learning_status"
        )
        is not None
    ):
        fail(
            "Passage 0005 possède déjà un "
            "statut d'apprentissage."
        )

    learning_events = [
        event
        for event in document.get(
            "change_history",
            [],
        )
        if (
            isinstance(event, dict)
            and event.get("event")
            == "logical_learning_recorded"
        )
    ]

    event_passages = {
        event.get("passage_id")
        for event in learning_events
    }

    missing_events = (
        set(EXPECTED)
        - event_passages
    )

    if missing_events:
        fail(
            "Événements durables absents : "
            + ", ".join(
                sorted(missing_events)
            )
        )

    external_notes = sum(
        encounter.get(
            "external_reading_note"
        )
        is not None
        for encounter in encounters.values()
    )

    collective_reviews = sum(
        encounter.get(
            "collective_review"
        )
        is not None
        for encounter in encounters.values()
    )

    after = JOURNAL.read_bytes()

    if before != after:
        fail(
            "Le journal a changé pendant "
            "l'audit en lecture seule."
        )

    print()
    print(
        "===== SÉPARATION DES COUCHES ====="
    )
    print(
        "Notes externes :",
        external_notes,
    )
    print(
        "Revues collectives :",
        collective_reviews,
    )
    print(
        "Apprentissages logiques :",
        4,
    )
    print(
        "Appel LLM pour ces apprentissages :",
        "non",
    )
    print(
        "Validation humaine requise pour exister :",
        "non",
    )

    print()
    print(
        "===== FILE D'ATTENTE ====="
    )
    print(
        "Passages 0001-0004 : processed"
    )
    print(
        "Passage 0005 :",
        passage_0005["status"],
    )
    print(
        "Apprentissage du passage 0005 :",
        passage_0005.get(
            "eliot_learning_status"
        ),
    )

    print()
    print(
        "Journal inchangé pendant l'audit :",
        True,
    )
    print("Audit global : OK")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(
            f"Audit global : ÉCHEC — {exc}",
            file=sys.stderr,
        )
        raise
