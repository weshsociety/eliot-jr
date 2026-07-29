from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any
import hashlib
import json
import re

from core.reading_source import (
    ReadingSourceError,
    build_reading_manifest,
)


JOURNAL_ID_PATTERN = re.compile(
    r"^[a-z0-9][a-z0-9_]*$"
)

CONTEXT_SCHEMA_VERSION = 1

FORBIDDEN_OUTPUT_KEYS = frozenset({
    "external_reading_note",
    "collective_review",
    "provisional_understanding",
    "what_passage_says",
    "questions_or_objections",
    "limits",
    "engine_attribution",
    "authorship_status",
    "epistemic_status",
    "review",
    "review_history",
    "validated_result",
    "request",
})

SELECTED_JOURNAL_FIELDS = {
    "root": (
        "schema_version",
        "journal_id",
        "status",
        "encounter_count",
    ),
    "work": (
        "work_id",
        "author",
        "title",
        "edition",
        "translator",
        "source_file",
        "source_status",
        "source_sha256",
        "source_size_bytes",
    ),
    "reading_queue": (
        "passage_id",
        "order",
        "passage_sha256",
        "status",
        "queued_at_utc",
        "exposed_at_utc",
        "eliot_learning_status",
    ),
    "encounters": (
        "encounter_id",
        "encounter_number",
        "passage_id",
        "passage_order",
        "passage_sha256",
        "encountered_at_utc",
        "passage_encounter",
    ),
}


class LogicalReadingContextError(
    ValueError
):
    """Erreur contrôlée lors de la construction du sas logique."""


def _canonical_json_bytes(
    value: Any,
) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(
    value: bytes,
) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_json_object(
    path: Path,
) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ) as exc:
        raise LogicalReadingContextError(
            f"Document JSON illisible : {path}"
        ) from exc

    if not isinstance(value, dict):
        raise LogicalReadingContextError(
            f"Objet JSON attendu : {path}"
        )

    return value


def _safe_journal_path(
    project_root: Path,
    journal_id: str,
) -> Path:
    journal_id = str(journal_id).strip()

    if not JOURNAL_ID_PATTERN.fullmatch(
        journal_id
    ):
        raise LogicalReadingContextError(
            "Identifiant de journal invalide."
        )

    root = project_root.resolve()

    path = (
        root
        / "curriculum"
        / "journaux"
        / f"{journal_id}.json"
    ).resolve()

    try:
        path.relative_to(root)
    except ValueError as exc:
        raise LogicalReadingContextError(
            "Le journal doit appartenir "
            "à la maison d’Eliot."
        ) from exc

    if not path.is_file():
        raise LogicalReadingContextError(
            f"Journal introuvable : {journal_id}"
        )

    return path


def _normalise_passage_record(
    passage: dict[str, Any],
) -> dict[str, Any]:
    return {
        "passage_id": str(
            passage.get(
                "passage_id",
                "",
            )
        ).strip(),
        "order": passage.get("order"),
        "passage_sha256": str(
            passage.get(
                "sha256",
                "",
            )
        ).strip(),
        "character_count": passage.get(
            "character_count"
        ),
        "word_count": passage.get(
            "word_count"
        ),
        "text": passage.get("text"),
    }


def _normalise_queue_item(
    item: dict[str, Any],
) -> dict[str, Any]:
    return {
        "passage_id": str(
            item.get(
                "passage_id",
                "",
            )
        ).strip(),
        "order": item.get("order"),
        "passage_sha256": str(
            item.get(
                "passage_sha256",
                "",
            )
        ).strip(),
        "status": item.get("status"),
        "queued_at_utc": item.get(
            "queued_at_utc"
        ),
        "exposed_at_utc": item.get(
            "exposed_at_utc"
        ),
        "eliot_learning_status": item.get(
            "eliot_learning_status"
        ),
    }


def _project_encounter(
    encounter: dict[str, Any],
) -> dict[str, Any]:
    passage_layer = encounter.get(
        "passage_encounter"
    )

    if not isinstance(passage_layer, dict):
        passage_layer = {}

    return {
        "encounter_id": passage_layer.get(
            "encounter_id",
            encounter.get("encounter_id"),
        ),
        "encounter_number": (
            passage_layer.get(
                "encounter_number",
                encounter.get(
                    "encounter_number"
                ),
            )
        ),
        "passage_id": str(
            passage_layer.get(
                "passage_id",
                encounter.get(
                    "passage_id",
                    "",
                ),
            )
        ).strip(),
        "passage_order": passage_layer.get(
            "passage_order",
            encounter.get("passage_order"),
        ),
        "passage_sha256": str(
            passage_layer.get(
                "passage_sha256",
                encounter.get(
                    "passage_sha256",
                    "",
                ),
            )
        ).strip(),
        "encountered_at_utc": (
            passage_layer.get(
                "encountered_at_utc",
                encounter.get(
                    "encountered_at_utc"
                ),
            )
        ),
    }


def _assert_no_forbidden_keys(
    value: Any,
    *,
    location: str = "$",
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in FORBIDDEN_OUTPUT_KEYS:
                raise LogicalReadingContextError(
                    "Namespace interdit dans "
                    f"le contexte logique : "
                    f"{location}.{key}"
                )

            _assert_no_forbidden_keys(
                child,
                location=f"{location}.{key}",
            )

    elif isinstance(value, list):
        for index, child in enumerate(value):
            _assert_no_forbidden_keys(
                child,
                location=(
                    f"{location}[{index}]"
                ),
            )


def _source_declares_partial(
    metadata: dict[str, Any],
) -> bool:
    values = " ".join(
        str(value).casefold()
        for value in metadata.values()
    )

    return any(
        marker in values
        for marker in (
            "extrait partiel",
            "corpus reçu s’arrête",
            "corpus recu s'arrete",
            "partial extract",
        )
    )


def _validate_manifest_against_journal(
    *,
    manifest: dict[str, Any],
    journal: dict[str, Any],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    work = journal.get("work")
    queue = journal.get("reading_queue")

    if not isinstance(work, dict):
        raise LogicalReadingContextError(
            "Section work invalide."
        )

    if not isinstance(queue, list):
        raise LogicalReadingContextError(
            "File de lecture invalide."
        )

    if (
        manifest.get("source_file")
        != work.get("source_file")
    ):
        raise LogicalReadingContextError(
            "Le manifeste et le journal "
            "ne désignent pas la même source."
        )

    if (
        manifest.get("source_sha256")
        != work.get("source_sha256")
    ):
        raise LogicalReadingContextError(
            "Le SHA-256 de la source "
            "ne correspond pas au journal."
        )

    if (
        manifest.get("source_size_bytes")
        != work.get("source_size_bytes")
    ):
        raise LogicalReadingContextError(
            "La taille de la source "
            "ne correspond pas au journal."
        )

    raw_passages = manifest.get("passages")

    if not isinstance(raw_passages, list):
        raise LogicalReadingContextError(
            "Passages du manifeste invalides."
        )

    manifest_passages = []

    for raw_passage in raw_passages:
        if not isinstance(raw_passage, dict):
            raise LogicalReadingContextError(
                "Passage de manifeste invalide."
            )

        manifest_passages.append(
            _normalise_passage_record(
                raw_passage
            )
        )

    queue_items = []

    for raw_item in queue:
        if not isinstance(raw_item, dict):
            raise LogicalReadingContextError(
                "Passage de file invalide."
            )

        queue_items.append(
            _normalise_queue_item(
                raw_item
            )
        )

    if len(manifest_passages) != len(
        queue_items
    ):
        raise LogicalReadingContextError(
            "Le manifeste et la file "
            "n’ont pas le même nombre "
            "de passages."
        )

    for expected_order, (
        passage,
        queue_item,
    ) in enumerate(
        zip(
            manifest_passages,
            queue_items,
            strict=True,
        ),
        1,
    ):
        if passage["order"] != expected_order:
            raise LogicalReadingContextError(
                "Ordre incohérent dans "
                "le manifeste."
            )

        if queue_item["order"] != expected_order:
            raise LogicalReadingContextError(
                "Ordre incohérent dans "
                "la file de lecture."
            )

        if (
            passage["passage_id"]
            != queue_item["passage_id"]
        ):
            raise LogicalReadingContextError(
                "Identifiant de passage "
                "incohérent entre le manifeste "
                "et la file."
            )

        if (
            passage["passage_sha256"]
            != queue_item[
                "passage_sha256"
            ]
        ):
            raise LogicalReadingContextError(
                "Empreinte de passage "
                "incohérente entre le manifeste "
                "et la file."
            )

    return (
        manifest_passages,
        queue_items,
    )


def _validate_encounters(
    *,
    journal: dict[str, Any],
    passages_by_id: dict[
        str,
        dict[str, Any],
    ],
) -> list[dict[str, Any]]:
    raw_encounters = journal.get(
        "encounters",
        [],
    )

    if not isinstance(raw_encounters, list):
        raise LogicalReadingContextError(
            "Liste des rencontres invalide."
        )

    projected = []
    seen_passages = set()
    seen_encounters = set()

    for raw_encounter in raw_encounters:
        if not isinstance(
            raw_encounter,
            dict,
        ):
            raise LogicalReadingContextError(
                "Rencontre invalide."
            )

        encounter = _project_encounter(
            raw_encounter
        )

        passage_id = encounter[
            "passage_id"
        ]

        if passage_id not in passages_by_id:
            raise LogicalReadingContextError(
                "Une rencontre désigne "
                "un passage inconnu."
            )

        if passage_id in seen_passages:
            raise LogicalReadingContextError(
                "Plusieurs rencontres sont "
                "attribuées au même passage."
            )

        encounter_id = encounter[
            "encounter_id"
        ]

        if not encounter_id:
            raise LogicalReadingContextError(
                "Identifiant de rencontre absent."
            )

        if encounter_id in seen_encounters:
            raise LogicalReadingContextError(
                "Identifiant de rencontre dupliqué."
            )

        passage = passages_by_id[
            passage_id
        ]

        if (
            encounter["passage_order"]
            != passage["order"]
        ):
            raise LogicalReadingContextError(
                "Ordre de rencontre incohérent."
            )

        if (
            encounter["passage_sha256"]
            != passage["passage_sha256"]
        ):
            raise LogicalReadingContextError(
                "Empreinte de rencontre "
                "incohérente."
            )

        if not encounter[
            "encountered_at_utc"
        ]:
            raise LogicalReadingContextError(
                "Date de rencontre absente."
            )

        projected.append(encounter)
        seen_passages.add(passage_id)
        seen_encounters.add(encounter_id)

    projected.sort(
        key=lambda item: (
            item.get(
                "encounter_number"
            )
            if isinstance(
                item.get(
                    "encounter_number"
                ),
                int,
            )
            else 10**9,
            item["passage_order"],
            item["passage_id"],
        )
    )

    declared_count = journal.get(
        "encounter_count",
        len(projected),
    )

    if declared_count != len(projected):
        raise LogicalReadingContextError(
            "Compteur de rencontres incohérent."
        )

    return projected


def build_logical_reading_context(
    *,
    project_root: Path,
    journal_id: str,
    passage_id: str,
    require_encountered: bool = True,
) -> dict[str, Any]:
    """
    Construit un sas déterministe pour une faculté non-LLM.

    Le fichier journal complet est nécessairement lu et parsé
    parce que ses couches vivent dans un seul document JSON.
    Seuls les champs explicitement autorisés sont cependant
    sélectionnés et projetés dans le contexte retourné.
    """
    root = project_root.resolve()
    journal_path = _safe_journal_path(
        root,
        journal_id,
    )
    journal = _read_json_object(
        journal_path
    )

    if (
        journal.get("journal_id")
        != journal_id
    ):
        raise LogicalReadingContextError(
            "L’identité interne du journal "
            "ne correspond pas au chemin."
        )

    work = journal.get("work")

    if not isinstance(work, dict):
        raise LogicalReadingContextError(
            "Section work invalide."
        )

    source_file = work.get(
        "source_file"
    )

    if not isinstance(
        source_file,
        str,
    ) or not source_file.strip():
        raise LogicalReadingContextError(
            "Chemin de source absent."
        )

    try:
        manifest, warnings = (
            build_reading_manifest(
                root,
                source_file,
            )
        )
    except ReadingSourceError as exc:
        raise LogicalReadingContextError(
            str(exc)
        ) from exc

    (
        manifest_passages,
        queue_items,
    ) = _validate_manifest_against_journal(
        manifest=manifest,
        journal=journal,
    )

    passages_by_id = {
        passage["passage_id"]: passage
        for passage in manifest_passages
    }

    queue_by_id = {
        item["passage_id"]: item
        for item in queue_items
    }

    passage_id = str(
        passage_id
    ).strip()

    if passage_id not in passages_by_id:
        raise LogicalReadingContextError(
            f"Passage inconnu : {passage_id}"
        )

    target_passage = passages_by_id[
        passage_id
    ]
    target_queue = queue_by_id[
        passage_id
    ]

    encounters = _validate_encounters(
        journal=journal,
        passages_by_id=passages_by_id,
    )

    encounter_by_passage = {
        encounter["passage_id"]: encounter
        for encounter in encounters
    }

    target_encounter = (
        encounter_by_passage.get(
            passage_id
        )
    )

    if require_encountered:
        if (
            target_queue["status"]
            != "encountered"
        ):
            raise LogicalReadingContextError(
                "Le passage n’est pas encore "
                "enregistré comme rencontré : "
                f"{passage_id}"
            )

        if target_encounter is None:
            raise LogicalReadingContextError(
                "La rencontre du passage "
                "est absente du journal."
            )

    if target_encounter is not None:
        encountered_at_utc = (
            target_encounter[
                "encountered_at_utc"
            ]
        )
        encounter_id = (
            target_encounter[
                "encounter_id"
            ]
        )
    else:
        encountered_at_utc = None
        encounter_id = None

    prior_encounters = [
        deepcopy(encounter)
        for encounter in encounters
        if (
            encounter["passage_order"]
            < target_passage["order"]
        )
    ]

    metadata = manifest.get(
        "metadata",
        {},
    )

    if not isinstance(metadata, dict):
        metadata = {}

    context: dict[str, Any] = {
        "schema_version": (
            CONTEXT_SCHEMA_VERSION
        ),
        "context_kind": (
            "deterministic_logical_"
            "reading_context"
        ),
        "producer": (
            "eliot_jr_logical_reading_"
            "context"
        ),
        "processing_mode": (
            "deterministic_non_llm"
        ),
        "llm_used": False,
        "journal": {
            "journal_id": journal_id,
            "journal_schema_version": (
                journal.get(
                    "schema_version"
                )
            ),
            "journal_status": (
                journal.get("status")
            ),
        },
        "work": {
            "work_id": work.get("work_id"),
            "author": work.get("author"),
            "title": work.get("title"),
            "edition": work.get(
                "edition"
            ),
            "translator": work.get(
                "translator"
            ),
        },
        "source": {
            "source_file": manifest.get(
                "source_file"
            ),
            "source_sha256": manifest.get(
                "source_sha256"
            ),
            "source_size_bytes": (
                manifest.get(
                    "source_size_bytes"
                )
            ),
            "source_status": work.get(
                "source_status"
            ),
            "metadata": deepcopy(
                metadata
            ),
            "warnings": list(warnings),
            "passage_count": manifest.get(
                "passage_count"
            ),
            "source_declares_partial_corpus": (
                _source_declares_partial(
                    metadata
                )
            ),
        },
        "passage": {
            **deepcopy(target_passage),
            "queue_status": target_queue[
                "status"
            ],
            "encounter_id": encounter_id,
            "encountered_at_utc": (
                encountered_at_utc
            ),
        },
        "chronology": {
            "prior_encounters": (
                prior_encounters
            ),
            "prior_encounter_count": len(
                prior_encounters
            ),
            "current_passage_order": (
                target_passage["order"]
            ),
        },
        "access_manifest": {
            "storage_files_read": [
                str(
                    journal_path.relative_to(
                        root
                    )
                ),
                str(
                    manifest.get(
                        "source_file"
                    )
                ),
            ],
            "journal_fields_selected": (
                deepcopy(
                    SELECTED_JOURNAL_FIELDS
                )
            ),
            "journal_namespaces_not_"
            "projected": sorted(
                FORBIDDEN_OUTPUT_KEYS
            ),
            "exposure_policy": (
                "Le journal JSON complet est "
                "lu au niveau stockage, mais "
                "seuls les champs autorisés "
                "sont projetés dans ce contexte."
            ),
            "external_note_content_exposed": (
                False
            ),
            "collective_review_content_exposed": (
                False
            ),
            "eliot_learning_state_content_exposed": (
                False
            ),
        },
    }

    _assert_no_forbidden_keys(
        context
    )

    context_hash = _sha256_bytes(
        _canonical_json_bytes(context)
    )

    context["context_sha256"] = (
        context_hash
    )
    context["context_id"] = (
        f"{journal_id}:{passage_id}:"
        f"{context_hash[:16]}"
    )

    _assert_no_forbidden_keys(
        context
    )

    return context
