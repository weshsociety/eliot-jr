from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator
import fcntl
import hashlib
import json
import os
import re
import tempfile

from core.reading_source import (
    ReadingSourceError,
    build_reading_manifest,
)
from gardien.backup_reading_state import (
    create_backup,
)


JOURNAL_ID_PATTERN = re.compile(
    r"^[a-z0-9][a-z0-9_]*$"
)

PRODUCER = (
    "eliot_jr_reading_encounter_registry"
)

ENCOUNTER_SCHEMA_VERSION = 2
LEARNING_SCHEMA_VERSION = 2


class ReadingEncounterRegistryError(
    ValueError
):
    """Erreur contrôlée du registre de rencontre."""


def _utc_now(
    now: datetime | None = None,
) -> str:
    moment = now or datetime.now(
        timezone.utc
    )

    if moment.tzinfo is None:
        moment = moment.replace(
            tzinfo=timezone.utc
        )

    return moment.astimezone(
        timezone.utc
    ).isoformat()


def _parse_utc(
    value: Any,
) -> datetime:
    if not isinstance(value, str):
        raise ReadingEncounterRegistryError(
            "Date de rencontre invalide."
        )

    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ReadingEncounterRegistryError(
            "Date de rencontre invalide."
        ) from exc

    if parsed.tzinfo is None:
        raise ReadingEncounterRegistryError(
            "La date de rencontre doit "
            "contenir un fuseau horaire."
        )

    return parsed.astimezone(
        timezone.utc
    )


def _canonical_json_bytes(
    value: Any,
) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _canonical_hash(
    value: Any,
) -> str:
    return hashlib.sha256(
        _canonical_json_bytes(value)
    ).hexdigest()


def _json_bytes(
    value: dict[str, Any],
) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    ).encode("utf-8")


def _journal_path(
    project_root: Path,
    journal_id: str,
) -> Path:
    journal_id = str(
        journal_id
    ).strip()

    if not JOURNAL_ID_PATTERN.fullmatch(
        journal_id
    ):
        raise ReadingEncounterRegistryError(
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
        raise ReadingEncounterRegistryError(
            "Le journal doit appartenir "
            "à la maison d’Eliot."
        ) from exc

    if not path.is_file():
        raise ReadingEncounterRegistryError(
            f"Journal introuvable : {journal_id}"
        )

    return path


def _read_json(
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
        raise ReadingEncounterRegistryError(
            f"Journal illisible : {path}"
        ) from exc

    if not isinstance(value, dict):
        raise ReadingEncounterRegistryError(
            "Le journal n’est pas "
            "un objet JSON."
        )

    return value


def _write_atomic_bytes(
    path: Path,
    payload: bytes,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    descriptor, temporary_name = (
        tempfile.mkstemp(
            prefix=path.name + ".",
            suffix=".tmp",
            dir=path.parent,
        )
    )

    try:
        with os.fdopen(
            descriptor,
            "wb",
        ) as temporary:
            temporary.write(payload)
            temporary.flush()
            os.fsync(
                temporary.fileno()
            )

        os.chmod(
            temporary_name,
            0o600,
        )
        os.replace(
            temporary_name,
            path,
        )

    except Exception:
        try:
            os.unlink(
                temporary_name
            )
        except OSError:
            pass

        raise


@contextmanager
def _exclusive_journal_lock(
    path: Path,
) -> Iterator[None]:
    lock_path = path.with_suffix(
        path.suffix + ".lock"
    )

    with lock_path.open(
        "a+",
        encoding="utf-8",
    ) as lock:
        lock_path.chmod(0o600)

        fcntl.flock(
            lock.fileno(),
            fcntl.LOCK_EX,
        )

        try:
            yield
        finally:
            fcntl.flock(
                lock.fileno(),
                fcntl.LOCK_UN,
            )


def _normalise_manifest_passage(
    passage: dict[str, Any],
) -> dict[str, Any]:
    passage_id = str(
        passage.get("passage_id", "")
    ).strip()

    passage_hash = str(
        passage.get(
            "sha256",
            passage.get(
                "passage_sha256",
                "",
            ),
        )
    ).strip()

    order = passage.get("order")

    if (
        not passage_id
        or not passage_hash
        or not isinstance(order, int)
        or order < 1
    ):
        raise ReadingEncounterRegistryError(
            "Passage de manifeste invalide."
        )

    return {
        "passage_id": passage_id,
        "order": order,
        "passage_sha256": passage_hash,
        "word_count": int(
            passage.get("word_count", 0)
        ),
        "character_count": int(
            passage.get(
                "character_count",
                0,
            )
        ),
    }


def _manifest_for_journal(
    *,
    root: Path,
    journal: dict[str, Any],
) -> tuple[
    dict[str, dict[str, Any]],
    list[str],
]:
    work = journal.get("work")

    if not isinstance(work, dict):
        raise ReadingEncounterRegistryError(
            "Section work invalide."
        )

    source_file = work.get(
        "source_file"
    )
    source_hash = str(
        work.get(
            "source_sha256",
            "",
        )
    ).strip()

    if (
        not isinstance(source_file, str)
        or not source_file.strip()
        or not source_hash
    ):
        raise ReadingEncounterRegistryError(
            "Source du journal incomplète."
        )

    try:
        manifest, warnings = (
            build_reading_manifest(
                root,
                source_file,
            )
        )
    except ReadingSourceError as exc:
        raise ReadingEncounterRegistryError(
            str(exc)
        ) from exc

    if not isinstance(manifest, dict):
        raise ReadingEncounterRegistryError(
            "Manifeste de lecture invalide."
        )

    if (
        str(
            manifest.get(
                "source_sha256",
                "",
            )
        ).strip()
        != source_hash
    ):
        raise ReadingEncounterRegistryError(
            "L’empreinte de la source "
            "diffère du journal."
        )

    raw_passages = manifest.get(
        "passages"
    )

    if not isinstance(
        raw_passages,
        list,
    ):
        raise ReadingEncounterRegistryError(
            "Passages du manifeste invalides."
        )

    passages: dict[
        str,
        dict[str, Any],
    ] = {}

    for raw in raw_passages:
        if not isinstance(raw, dict):
            raise ReadingEncounterRegistryError(
                "Passage du manifeste invalide."
            )

        passage = _normalise_manifest_passage(
            raw
        )
        passage_id = passage[
            "passage_id"
        ]

        if passage_id in passages:
            raise ReadingEncounterRegistryError(
                "Passage dupliqué dans "
                "le manifeste."
            )

        passages[passage_id] = passage

    warning_strings = [
        str(warning)
        for warning in (
            warnings
            if isinstance(warnings, list)
            else []
        )
    ]

    return passages, warning_strings


def _validate_queue(
    journal: dict[str, Any],
    manifest_passages: dict[
        str,
        dict[str, Any],
    ],
) -> list[dict[str, Any]]:
    queue = journal.get(
        "reading_queue"
    )

    if not isinstance(queue, list):
        raise ReadingEncounterRegistryError(
            "File de lecture invalide."
        )

    if len(queue) != len(
        manifest_passages
    ):
        raise ReadingEncounterRegistryError(
            "La file et le manifeste "
            "n’ont pas la même taille."
        )

    seen = set()

    for expected_order, item in enumerate(
        queue,
        1,
    ):
        if not isinstance(item, dict):
            raise ReadingEncounterRegistryError(
                "Entrée de file invalide."
            )

        passage_id = str(
            item.get(
                "passage_id",
                "",
            )
        ).strip()

        if (
            not passage_id
            or passage_id in seen
        ):
            raise ReadingEncounterRegistryError(
                "Identifiant de file invalide "
                "ou dupliqué."
            )

        manifest_passage = (
            manifest_passages.get(
                passage_id
            )
        )

        if manifest_passage is None:
            raise ReadingEncounterRegistryError(
                "La file désigne un passage "
                "absent du manifeste."
            )

        if (
            item.get("order")
            != expected_order
            or item.get("order")
            != manifest_passage["order"]
        ):
            raise ReadingEncounterRegistryError(
                "Ordre de file incohérent."
            )

        if (
            item.get(
                "passage_sha256"
            )
            != manifest_passage[
                "passage_sha256"
            ]
        ):
            raise ReadingEncounterRegistryError(
                "Empreinte de passage "
                "incohérente dans la file."
            )

        if int(
            item.get("word_count", 0)
        ) != manifest_passage[
            "word_count"
        ]:
            raise ReadingEncounterRegistryError(
                "Nombre de mots incohérent "
                "dans la file."
            )

        if int(
            item.get(
                "character_count",
                0,
            )
        ) != manifest_passage[
            "character_count"
        ]:
            raise ReadingEncounterRegistryError(
                "Nombre de caractères "
                "incohérent dans la file."
            )

        seen.add(passage_id)

    return queue


def _encounter_passage_id(
    encounter: dict[str, Any],
) -> str:
    passage_id = str(
        encounter.get(
            "passage_id",
            "",
        )
    ).strip()

    if passage_id:
        return passage_id

    layer = encounter.get(
        "passage_encounter"
    )

    if isinstance(layer, dict):
        return str(
            layer.get(
                "passage_id",
                "",
            )
        ).strip()

    return ""


def _encounter_identity(
    encounter: dict[str, Any],
) -> tuple[
    str,
    str,
]:
    encounter_id = str(
        encounter.get(
            "encounter_id",
            "",
        )
    ).strip()

    layer = encounter.get(
        "passage_encounter"
    )

    if not encounter_id and isinstance(
        layer,
        dict,
    ):
        encounter_id = str(
            layer.get(
                "encounter_id",
                "",
            )
        ).strip()

    return (
        _encounter_passage_id(
            encounter
        ),
        encounter_id,
    )


def _validate_existing_encounters(
    journal: dict[str, Any],
    manifest_passages: dict[
        str,
        dict[str, Any],
    ],
) -> list[dict[str, Any]]:
    encounters = journal.get(
        "encounters"
    )

    if not isinstance(
        encounters,
        list,
    ):
        raise ReadingEncounterRegistryError(
            "Liste des rencontres invalide."
        )

    declared_count = journal.get(
        "encounter_count",
        len(encounters),
    )

    if declared_count != len(encounters):
        raise ReadingEncounterRegistryError(
            "Compteur de rencontres "
            "incohérent."
        )

    seen_passages = set()
    seen_ids = set()
    numbers = []

    for encounter in encounters:
        if not isinstance(
            encounter,
            dict,
        ):
            raise ReadingEncounterRegistryError(
                "Rencontre invalide."
            )

        passage_id, encounter_id = (
            _encounter_identity(
                encounter
            )
        )

        if (
            not passage_id
            or passage_id in seen_passages
            or not encounter_id
            or encounter_id in seen_ids
        ):
            raise ReadingEncounterRegistryError(
                "Identité de rencontre "
                "invalide ou dupliquée."
            )

        passage = manifest_passages.get(
            passage_id
        )

        if passage is None:
            raise ReadingEncounterRegistryError(
                "Une rencontre désigne "
                "un passage inconnu."
            )

        layer = encounter.get(
            "passage_encounter"
        )

        if not isinstance(layer, dict):
            raise ReadingEncounterRegistryError(
                "Couche passage_encounter "
                "absente."
            )

        if (
            layer.get("status")
            != "recorded"
            or layer.get("passage_id")
            != passage_id
            or layer.get("passage_order")
            != passage["order"]
            or layer.get(
                "passage_sha256"
            )
            != passage["passage_sha256"]
        ):
            raise ReadingEncounterRegistryError(
                "Couche de rencontre "
                "incohérente."
            )

        number = layer.get(
            "encounter_number",
            encounter.get(
                "encounter_number"
            ),
        )

        if (
            not isinstance(number, int)
            or number < 1
        ):
            raise ReadingEncounterRegistryError(
                "Numéro de rencontre invalide."
            )

        _parse_utc(
            layer.get(
                "encountered_at_utc",
                encounter.get(
                    "encountered_at_utc"
                ),
            )
        )

        numbers.append(number)
        seen_passages.add(passage_id)
        seen_ids.add(encounter_id)

    if sorted(numbers) != list(
        range(1, len(encounters) + 1)
    ):
        raise ReadingEncounterRegistryError(
            "Chronologie numérotée "
            "incohérente."
        )

    return encounters


def _find_queue_index(
    queue: list[dict[str, Any]],
    passage_id: str,
) -> int:
    matches = [
        index
        for index, item in enumerate(
            queue
        )
        if item.get("passage_id")
        == passage_id
    ]

    if len(matches) != 1:
        raise ReadingEncounterRegistryError(
            "Le passage doit apparaître "
            "une seule fois dans la file."
        )

    return matches[0]


def _find_existing_encounter(
    encounters: list[dict[str, Any]],
    passage_id: str,
) -> dict[str, Any] | None:
    matches = [
        encounter
        for encounter in encounters
        if _encounter_passage_id(
            encounter
        )
        == passage_id
    ]

    if len(matches) > 1:
        raise ReadingEncounterRegistryError(
            "Plusieurs rencontres existent "
            "pour ce passage."
        )

    return (
        matches[0]
        if matches
        else None
    )


def _initial_learning_state() -> dict[str, Any]:
    return {
        "schema_version": (
            LEARNING_SCHEMA_VERSION
        ),
        "status": "not_yet_processed",
        "processing_mode": (
            "deterministic_non_llm"
        ),
        "processed_at_utc": None,
        "producer": (
            "eliot_jr_logical_core"
        ),
        "llm_used": False,
        "human_approval_required_to_exist": (
            False
        ),
        "conclusion_required": False,
        "may_remain_unresolved": True,
        "may_hold_contradictions": True,
        "may_disagree_with_collective": True,
        "claims": [],
        "terms": [],
        "relations": [],
        "reference_forms": [],
        "ambiguities": [],
        "questions": [],
        "contradictions": [],
        "hypotheses": [],
        "revisions": [],
    }


def _encounter_id(
    *,
    journal_id: str,
    passage: dict[str, Any],
) -> str:
    identity = {
        "operation": (
            "deterministic_passage_"
            "encounter"
        ),
        "journal_id": journal_id,
        "passage_id": passage[
            "passage_id"
        ],
        "passage_order": passage[
            "order"
        ],
        "passage_sha256": passage[
            "passage_sha256"
        ],
    }

    suffix = _canonical_hash(
        identity
    )[:16]

    return (
        f"{journal_id}:"
        f"{passage['passage_id']}:"
        f"{suffix}"
    )


def _build_encounter(
    *,
    journal_id: str,
    passage: dict[str, Any],
    encounter_number: int,
    timestamp: str,
) -> dict[str, Any]:
    encounter_id = _encounter_id(
        journal_id=journal_id,
        passage=passage,
    )

    encounter: dict[str, Any] = {
        "schema_version": (
            ENCOUNTER_SCHEMA_VERSION
        ),
        "record_kind": (
            "reading_encounter"
        ),
        "encounter_id": encounter_id,
        "encounter_number": (
            encounter_number
        ),
        "passage_id": passage[
            "passage_id"
        ],
        "passage_order": passage[
            "order"
        ],
        "passage_sha256": passage[
            "passage_sha256"
        ],
        "encountered_at_utc": timestamp,
        "passage_encounter": {
            "status": "recorded",
            "encounter_id": encounter_id,
            "encounter_number": (
                encounter_number
            ),
            "passage_id": passage[
                "passage_id"
            ],
            "passage_order": passage[
                "order"
            ],
            "passage_sha256": passage[
                "passage_sha256"
            ],
            "encountered_at_utc": (
                timestamp
            ),
        },
        "external_reading_note": {
            "status": "not_recorded",
            "producer": None,
            "engine_id": None,
            "created_at_utc": None,
            "llm_used": False,
            "reason": (
                "no_external_reading_"
                "requested"
            ),
        },
        "collective_review": {
            "status": "not_recorded",
            "reviewed_at_utc": None,
            "reviewed_by": None,
            "human_approval_required_"
            "for_encounter": False,
            "reason": (
                "no_collective_review_"
                "requested"
            ),
        },
        "eliot_learning_state": (
            _initial_learning_state()
        ),
        "integration": {
            "performed_by": PRODUCER,
            "operation": (
                "deterministic_passage_"
                "encounter"
            ),
            "does_not_imply_"
            "interpretation": True,
            "does_not_imply_"
            "eliot_agreement": True,
            "external_model_called": (
                False
            ),
            "human_approval_required": (
                False
            ),
        },
    }

    hash_payload = deepcopy(
        encounter
    )

    encounter[
        "encounter_sha256"
    ] = _canonical_hash(
        hash_payload
    )

    return encounter


def _verify_encounter_hash(
    encounter: dict[str, Any],
) -> None:
    recorded = encounter.get(
        "encounter_sha256"
    )

    payload = deepcopy(
        encounter
    )
    payload.pop(
        "encounter_sha256",
        None,
    )

    expected = _canonical_hash(
        payload
    )

    if recorded != expected:
        raise ReadingEncounterRegistryError(
            "Empreinte de rencontre "
            "invalide."
        )


def _protected_existing_layers(
    encounters: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    protected = {}

    for encounter in encounters:
        passage_id = (
            _encounter_passage_id(
                encounter
            )
        )

        protected[passage_id] = {
            "passage_encounter": (
                deepcopy(
                    encounter.get(
                        "passage_encounter"
                    )
                )
            ),
            "external_reading_note": (
                deepcopy(
                    encounter.get(
                        "external_reading_note"
                    )
                )
            ),
            "collective_review": (
                deepcopy(
                    encounter.get(
                        "collective_review"
                    )
                )
            ),
            "eliot_learning_state": (
                deepcopy(
                    encounter.get(
                        "eliot_learning_state"
                    )
                )
            ),
        }

    return protected


def _verify_persisted_update(
    *,
    before_journal: dict[str, Any],
    after_journal: dict[str, Any],
    passage_id: str,
    encounter_id: str,
    encounter_hash: str,
) -> None:
    before_encounters = before_journal[
        "encounters"
    ]
    after_encounters = after_journal.get(
        "encounters"
    )

    if not isinstance(
        after_encounters,
        list,
    ):
        raise ReadingEncounterRegistryError(
            "Rencontres absentes après "
            "écriture."
        )

    if len(after_encounters) != (
        len(before_encounters) + 1
    ):
        raise ReadingEncounterRegistryError(
            "Nombre de rencontres "
            "incorrect après écriture."
        )

    if after_journal.get(
        "encounter_count"
    ) != len(after_encounters):
        raise ReadingEncounterRegistryError(
            "Compteur de rencontres "
            "incorrect après écriture."
        )

    before_protected = (
        _protected_existing_layers(
            before_encounters
        )
    )
    after_existing = [
        encounter
        for encounter in after_encounters
        if _encounter_passage_id(
            encounter
        )
        != passage_id
    ]
    after_protected = (
        _protected_existing_layers(
            after_existing
        )
    )

    if before_protected != after_protected:
        raise ReadingEncounterRegistryError(
            "Une rencontre antérieure a "
            "été modifiée par erreur."
        )

    encounter = _find_existing_encounter(
        after_encounters,
        passage_id,
    )

    if encounter is None:
        raise ReadingEncounterRegistryError(
            "Nouvelle rencontre absente "
            "après écriture."
        )

    if (
        encounter.get("encounter_id")
        != encounter_id
        or encounter.get(
            "encounter_sha256"
        )
        != encounter_hash
    ):
        raise ReadingEncounterRegistryError(
            "Identité de rencontre "
            "incorrecte après écriture."
        )

    _verify_encounter_hash(
        encounter
    )

    queue = after_journal.get(
        "reading_queue"
    )

    if not isinstance(queue, list):
        raise ReadingEncounterRegistryError(
            "File absente après écriture."
        )

    queue_index = _find_queue_index(
        queue,
        passage_id,
    )
    queue_item = queue[queue_index]

    if (
        queue_item.get("status")
        != "encountered"
        or queue_item.get(
            "encounter_id"
        )
        != encounter_id
        or queue_item.get(
            "eliot_learning_status"
        )
        != "not_yet_processed"
    ):
        raise ReadingEncounterRegistryError(
            "File non synchronisée après "
            "la rencontre."
        )


def record_reading_encounter(
    *,
    project_root: Path,
    journal_id: str,
    passage_id: str,
    now: datetime | None = None,
    commit: bool = True,
    backup_root: Path | None = None,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
]:
    """
    Fait entrer le prochain passage dans la chronologie.

    Aucun LLM n’est appelé. Aucune note externe, revue,
    interprétation, hypothèse ou conclusion n’est produite.
    L’existence de la rencontre ne dépend d’aucune validation
    humaine.
    """
    root = project_root.resolve()
    path = _journal_path(
        root,
        journal_id,
    )
    passage_id = str(
        passage_id
    ).strip()

    if not passage_id:
        raise ReadingEncounterRegistryError(
            "Identifiant de passage absent."
        )

    timestamp = _utc_now(now)
    timestamp_value = _parse_utc(
        timestamp
    )

    resolved_backup_root = (
        backup_root.resolve()
        if backup_root is not None
        else None
    )

    with _exclusive_journal_lock(
        path
    ):
        original_bytes = path.read_bytes()
        journal = _read_json(path)

        if (
            journal.get("journal_id")
            != journal_id
        ):
            raise ReadingEncounterRegistryError(
                "L’identité interne du "
                "journal est incohérente."
            )

        if journal.get(
            "schema_version"
        ) != 2:
            raise ReadingEncounterRegistryError(
                "Le registre exige un "
                "journal de schéma v2."
            )

        (
            manifest_passages,
            manifest_warnings,
        ) = _manifest_for_journal(
            root=root,
            journal=journal,
        )

        queue = _validate_queue(
            journal,
            manifest_passages,
        )
        encounters = (
            _validate_existing_encounters(
                journal,
                manifest_passages,
            )
        )

        if passage_id not in (
            manifest_passages
        ):
            raise ReadingEncounterRegistryError(
                f"Passage inconnu : {passage_id}"
            )

        queue_index = _find_queue_index(
            queue,
            passage_id,
        )
        queue_item = queue[
            queue_index
        ]
        passage = manifest_passages[
            passage_id
        ]
        existing_encounter = (
            _find_existing_encounter(
                encounters,
                passage_id,
            )
        )

        if (
            queue_item.get("status")
            == "encountered"
            and existing_encounter is not None
        ):
            layer = existing_encounter.get(
                "passage_encounter"
            )

            if not isinstance(layer, dict):
                raise ReadingEncounterRegistryError(
                    "Rencontre existante "
                    "invalide."
                )

            return journal, {
                "journal_id": journal_id,
                "passage_id": passage_id,
                "event": (
                    "reading_encounter_"
                    "already_recorded"
                ),
                "encounter_id": (
                    layer.get(
                        "encounter_id"
                    )
                ),
                "encounter_number": (
                    layer.get(
                        "encounter_number"
                    )
                ),
                "encounter_sha256": (
                    existing_encounter.get(
                        "encounter_sha256"
                    )
                ),
                "already_recorded": True,
                "committed": False,
                "backup_created": False,
                "llm_used": False,
                "human_approval_required": (
                    False
                ),
            }

        if (
            queue_item.get("status")
            == "encountered"
            or existing_encounter is not None
        ):
            raise ReadingEncounterRegistryError(
                "La file et les rencontres "
                "sont désynchronisées."
            )

        if queue_item.get(
            "status"
        ) != "queued":
            raise ReadingEncounterRegistryError(
                "Le passage n’est pas dans "
                "l’état queued."
            )

        expected_order = (
            len(encounters) + 1
        )

        if (
            passage["order"]
            != expected_order
            or queue_index
            != expected_order - 1
        ):
            raise ReadingEncounterRegistryError(
                "Seul le prochain passage "
                "chronologique peut être "
                "rencontré."
            )

        for prior in queue[
            :queue_index
        ]:
            if prior.get(
                "status"
            ) != "encountered":
                raise ReadingEncounterRegistryError(
                    "Un passage antérieur "
                    "n’est pas encore "
                    "rencontré."
                )

        for later in queue[
            queue_index + 1:
        ]:
            if later.get(
                "status"
            ) != "queued":
                raise ReadingEncounterRegistryError(
                    "Un passage ultérieur "
                    "possède déjà un état "
                    "inattendu."
                )

        prior_dates = []

        for encounter in encounters:
            layer = encounter[
                "passage_encounter"
            ]
            prior_dates.append(
                _parse_utc(
                    layer.get(
                        "encountered_at_utc"
                    )
                )
            )

        if (
            prior_dates
            and timestamp_value
            < max(prior_dates)
        ):
            raise ReadingEncounterRegistryError(
                "La nouvelle rencontre ne "
                "peut pas précéder une "
                "rencontre antérieure."
            )

        encounter = _build_encounter(
            journal_id=journal_id,
            passage=passage,
            encounter_number=(
                expected_order
            ),
            timestamp=timestamp,
        )

        updated = deepcopy(
            journal
        )
        updated[
            "encounters"
        ] = [
            *updated["encounters"],
            encounter,
        ]
        updated[
            "encounter_count"
        ] = len(
            updated["encounters"]
        )

        updated_queue_item = (
            updated[
                "reading_queue"
            ][queue_index]
        )

        updated_queue_item[
            "status"
        ] = "encountered"
        updated_queue_item[
            "exposed_at_utc"
        ] = timestamp
        updated_queue_item[
            "encounter_id"
        ] = encounter[
            "encounter_id"
        ]
        updated_queue_item[
            "encounter_number"
        ] = encounter[
            "encounter_number"
        ]
        updated_queue_item[
            "encounter_sha256"
        ] = encounter[
            "encounter_sha256"
        ]
        updated_queue_item[
            "encounter_registry"
        ] = PRODUCER
        updated_queue_item[
            "eliot_learning_status"
        ] = "not_yet_processed"

        history = updated.get(
            "change_history"
        )

        if not isinstance(
            history,
            list,
        ):
            raise ReadingEncounterRegistryError(
                "Historique du journal "
                "invalide."
            )

        history_event = {
            "event": (
                "reading_encounter_"
                "recorded"
            ),
            "at_utc": timestamp,
            "by": PRODUCER,
            "passage_id": passage_id,
            "passage_order": passage[
                "order"
            ],
            "passage_sha256": passage[
                "passage_sha256"
            ],
            "encounter_id": encounter[
                "encounter_id"
            ],
            "encounter_number": (
                encounter[
                    "encounter_number"
                ]
            ),
            "encounter_sha256": (
                encounter[
                    "encounter_sha256"
                ]
            ),
            "llm_used": False,
            "external_reading_note_"
            "produced": False,
            "collective_review_"
            "produced": False,
            "human_approval_required": (
                False
            ),
        }

        updated[
            "change_history"
        ] = [
            *history,
            history_event,
        ]

        report = {
            "journal_id": journal_id,
            "passage_id": passage_id,
            "event": (
                "reading_encounter_"
                "recorded"
            ),
            "encounter_id": encounter[
                "encounter_id"
            ],
            "encounter_number": (
                encounter[
                    "encounter_number"
                ]
            ),
            "encounter_sha256": (
                encounter[
                    "encounter_sha256"
                ]
            ),
            "manifest_warning_count": len(
                manifest_warnings
            ),
            "already_recorded": False,
            "committed": commit,
            "llm_used": False,
            "external_reading_note_"
            "produced": False,
            "collective_review_"
            "produced": False,
            "human_approval_required": (
                False
            ),
        }

        if not commit:
            return updated, {
                **report,
                "backup_created": False,
            }

        try:
            pre_backup = create_backup(
                project_root=root,
                backup_root=(
                    resolved_backup_root
                ),
            )
        except Exception as exc:
            raise ReadingEncounterRegistryError(
                "Sauvegarde préalable "
                "impossible ; aucune écriture "
                "n’a été effectuée."
            ) from exc

        try:
            _write_atomic_bytes(
                path,
                _json_bytes(updated),
            )

            persisted = _read_json(
                path
            )

            _verify_persisted_update(
                before_journal=journal,
                after_journal=persisted,
                passage_id=passage_id,
                encounter_id=encounter[
                    "encounter_id"
                ],
                encounter_hash=encounter[
                    "encounter_sha256"
                ],
            )

            post_backup = create_backup(
                project_root=root,
                backup_root=(
                    resolved_backup_root
                ),
            )

        except Exception as exc:
            try:
                _write_atomic_bytes(
                    path,
                    original_bytes,
                )
            except Exception as rollback_exc:
                raise ReadingEncounterRegistryError(
                    "Échec de la rencontre et "
                    "échec de la restauration "
                    "du journal."
                ) from rollback_exc

            raise ReadingEncounterRegistryError(
                "Transaction de rencontre "
                "annulée ; le journal "
                "original a été restauré."
            ) from exc

        return persisted, {
            **report,
            "backup_created": True,
            "pre_backup": pre_backup,
            "post_backup": post_backup,
        }
