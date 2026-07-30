from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json
import shutil
import tempfile

import core.reading_encounter_registry as registry
from core.logical_reading_context import (
    build_logical_reading_context,
)
from core.reading_encounter_registry import (
    ReadingEncounterRegistryError,
    record_reading_encounter,
)
from core.reading_schema_v2 import (
    _encounter_is_v2,
)


LIVE_ROOT = Path("/home/eliot-jr")
JOURNAL_ID = (
    "lecture_thoreau_desobeissance_civile"
)
PASSAGE_ID = "passage_0005"

SOURCE_RELATIVE = (
    "curriculum/sources/"
    "thoreau_desobeissance_civile_extrait_en.txt"
)
JOURNAL_RELATIVE = (
    "curriculum/journaux/"
    f"{JOURNAL_ID}.json"
)
CANDIDATES_RELATIVE = (
    ".memory/reading_candidates"
)


def sha256(
    path: Path,
) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def live_paths() -> list[Path]:
    return [
        LIVE_ROOT / SOURCE_RELATIVE,
        LIVE_ROOT / JOURNAL_RELATIVE,
        *sorted(
            (
                LIVE_ROOT
                / CANDIDATES_RELATIVE
            ).glob("*.json")
        ),
    ]


def live_hashes() -> dict[str, str]:
    return {
        str(path): sha256(path)
        for path in live_paths()
    }


def copy_state(
    destination: Path,
) -> None:
    for relative in (
        SOURCE_RELATIVE,
        JOURNAL_RELATIVE,
    ):
        source = LIVE_ROOT / relative
        target = destination / relative

        target.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        shutil.copy2(
            source,
            target,
        )

    candidates_target = (
        destination
        / CANDIDATES_RELATIVE
    )
    candidates_target.mkdir(
        parents=True,
        exist_ok=True,
    )

    for source in (
        LIVE_ROOT
        / CANDIDATES_RELATIVE
    ).glob("*.json"):
        shutil.copy2(
            source,
            candidates_target
            / source.name,
        )


def journal_path(
    root: Path,
) -> Path:
    return (
        root
        / JOURNAL_RELATIVE
    )


def load_journal(
    root: Path,
) -> dict[str, Any]:
    return json.loads(
        journal_path(root).read_text(
            encoding="utf-8"
        )
    )


def encounter_for(
    journal: dict[str, Any],
    passage_id: str,
) -> dict[str, Any]:
    matches = [
        encounter
        for encounter in journal[
            "encounters"
        ]
        if (
            encounter.get(
                "passage_id"
            )
            == passage_id
            or encounter.get(
                "passage_encounter",
                {},
            ).get(
                "passage_id"
            )
            == passage_id
        )
    ]

    assert len(matches) == 1
    return matches[0]


def queue_for(
    journal: dict[str, Any],
    passage_id: str,
) -> dict[str, Any]:
    matches = [
        item
        for item in journal[
            "reading_queue"
        ]
        if item.get(
            "passage_id"
        )
        == passage_id
    ]

    assert len(matches) == 1
    return matches[0]


def canonical(
    value: Any,
) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def protected_existing_layers(
    journal: dict[str, Any],
) -> dict[str, str]:
    protected = {}

    for passage_id in (
        "passage_0001",
        "passage_0002",
        "passage_0003",
        "passage_0004",
    ):
        encounter = encounter_for(
            journal,
            passage_id,
        )

        protected[passage_id] = (
            canonical({
                "passage_encounter": (
                    encounter.get(
                        "passage_encounter"
                    )
                ),
                "external_reading_note": (
                    encounter.get(
                        "external_reading_note"
                    )
                ),
                "collective_review": (
                    encounter.get(
                        "collective_review"
                    )
                ),
                "eliot_learning_state": (
                    encounter.get(
                        "eliot_learning_state"
                    )
                ),
            })
        )

    return protected


live_before = live_hashes()
assert len(live_before) == 6

with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    copy_state(root)

    backup_root = (
        root
        / ".backups"
        / "reading"
    )
    path = journal_path(root)
    original_bytes = path.read_bytes()
    original = load_journal(root)
    original_protected = (
        protected_existing_layers(
            original
        )
    )

    preview, preview_report = (
        record_reading_encounter(
            project_root=root,
            journal_id=JOURNAL_ID,
            passage_id=PASSAGE_ID,
            now=datetime(
                2026,
                7,
                30,
                1,
                0,
                tzinfo=timezone.utc,
            ),
            commit=False,
            backup_root=backup_root,
        )
    )

    assert (
        preview_report["event"]
        == "reading_encounter_recorded"
    )
    assert (
        preview_report["committed"]
        is False
    )
    assert path.read_bytes() == original_bytes
    assert (
        preview["encounter_count"]
        == 5
    )

    out_of_order_error = ""

    try:
        record_reading_encounter(
            project_root=root,
            journal_id=JOURNAL_ID,
            passage_id="passage_0006",
            now=datetime(
                2026,
                7,
                30,
                1,
                1,
                tzinfo=timezone.utc,
            ),
            commit=False,
            backup_root=backup_root,
        )
    except ReadingEncounterRegistryError as exc:
        out_of_order_error = str(exc)

    assert out_of_order_error

    persisted, first_report = (
        record_reading_encounter(
            project_root=root,
            journal_id=JOURNAL_ID,
            passage_id=PASSAGE_ID,
            now=datetime(
                2026,
                7,
                30,
                1,
                2,
                tzinfo=timezone.utc,
            ),
            commit=True,
            backup_root=backup_root,
        )
    )

    assert (
        first_report["event"]
        == "reading_encounter_recorded"
    )
    assert (
        first_report["committed"]
        is True
    )
    assert (
        first_report[
            "backup_created"
        ]
        is True
    )
    assert (
        persisted["encounter_count"]
        == 5
    )
    assert (
        len(persisted["encounters"])
        == 5
    )

    new_encounter = encounter_for(
        persisted,
        PASSAGE_ID,
    )
    new_queue = queue_for(
        persisted,
        PASSAGE_ID,
    )

    assert _encounter_is_v2(
        new_encounter
    )
    assert (
        new_encounter["record_kind"]
        == "reading_encounter"
    )
    assert (
        new_encounter[
            "encounter_number"
        ]
        == 5
    )
    assert (
        new_encounter[
            "passage_encounter"
        ]["status"]
        == "recorded"
    )
    assert (
        new_encounter[
            "external_reading_note"
        ]["status"]
        == "not_recorded"
    )
    assert (
        new_encounter[
            "collective_review"
        ]["status"]
        == "not_recorded"
    )

    learning = new_encounter[
        "eliot_learning_state"
    ]

    assert (
        learning["status"]
        == "not_yet_processed"
    )
    assert (
        learning[
            "processing_mode"
        ]
        == "deterministic_non_llm"
    )
    assert learning[
        "llm_used"
    ] is False
    assert (
        learning[
            "human_approval_required_to_exist"
        ]
        is False
    )

    assert (
        new_queue["status"]
        == "encountered"
    )
    assert (
        new_queue[
            "eliot_learning_status"
        ]
        == "not_yet_processed"
    )
    assert (
        new_queue["encounter_id"]
        == new_encounter[
            "encounter_id"
        ]
    )

    assert (
        protected_existing_layers(
            persisted
        )
        == original_protected
    )

    context = (
        build_logical_reading_context(
            project_root=root,
            journal_id=JOURNAL_ID,
            passage_id=PASSAGE_ID,
        )
    )

    assert (
        context["passage"][
            "encounter_id"
        ]
        == new_encounter[
            "encounter_id"
        ]
    )
    assert (
        context["passage"][
            "encountered_at_utc"
        ]
        == new_encounter[
            "encountered_at_utc"
        ]
    )

    committed_bytes = (
        path.read_bytes()
    )
    backups_before_repeat = len(
        list(
            backup_root.glob(
                "*.manifest.json"
            )
        )
    )

    repeated, repeat_report = (
        record_reading_encounter(
            project_root=root,
            journal_id=JOURNAL_ID,
            passage_id=PASSAGE_ID,
            commit=True,
            backup_root=backup_root,
        )
    )

    assert (
        repeat_report["event"]
        == (
            "reading_encounter_"
            "already_recorded"
        )
    )
    assert (
        repeat_report["committed"]
        is False
    )
    assert (
        path.read_bytes()
        == committed_bytes
    )
    assert (
        repeated
        == persisted
    )
    assert len(
        list(
            backup_root.glob(
                "*.manifest.json"
            )
        )
    ) == backups_before_repeat

    assert len(
        list(
            backup_root.glob(
                "*.manifest.json"
            )
        )
    ) == 2

with tempfile.TemporaryDirectory() as temp:
    rollback_root = Path(temp)
    copy_state(
        rollback_root
    )

    rollback_path = journal_path(
        rollback_root
    )
    rollback_original = (
        rollback_path.read_bytes()
    )
    rollback_backup_root = (
        rollback_root
        / ".backups"
        / "reading"
    )

    real_create_backup = (
        registry.create_backup
    )
    calls = 0

    def failing_backup(
        **kwargs: Any,
    ) -> dict[str, Any]:
        nonlocal_calls[0] += 1

        if nonlocal_calls[0] == 2:
            raise RuntimeError(
                "échec artificiel "
                "post-écriture"
            )

        return real_create_backup(
            **kwargs
        )

    nonlocal_calls = [0]
    registry.create_backup = (
        failing_backup
    )
    rollback_error = ""

    try:
        record_reading_encounter(
            project_root=rollback_root,
            journal_id=JOURNAL_ID,
            passage_id=PASSAGE_ID,
            now=datetime(
                2026,
                7,
                30,
                1,
                3,
                tzinfo=timezone.utc,
            ),
            commit=True,
            backup_root=(
                rollback_backup_root
            ),
        )
    except ReadingEncounterRegistryError as exc:
        rollback_error = str(exc)
    finally:
        registry.create_backup = (
            real_create_backup
        )

    assert rollback_error
    assert (
        rollback_path.read_bytes()
        == rollback_original
    )

live_after = live_hashes()
assert live_before == live_after

print(
    "===== REGISTRE DE RENCONTRE ====="
)
print(
    "Prévisualisation sans écriture :",
    True,
)
print(
    "Rencontre enregistrée :",
    first_report["event"],
)
print(
    "Identifiant déterministe :",
    first_report["encounter_id"],
)
print(
    "Numéro de rencontre :",
    first_report[
        "encounter_number"
    ],
)
print(
    "Rencontre reconnue v2 :",
    True,
)
print(
    "Note externe produite :",
    False,
)
print(
    "Revue collective produite :",
    False,
)
print(
    "Apprentissage initial :",
    "not_yet_processed",
)
print(
    "Contexte logique disponible :",
    True,
)
print(
    "Idempotence :",
    repeat_report["event"],
)
print(
    "Passage hors ordre refusé :",
    out_of_order_error,
)
print(
    "Restauration après échec :",
    rollback_error,
)
print(
    "Rencontres 0001-0004 inchangées :",
    True,
)
print(
    "États vivants inchangés :",
    live_before == live_after,
)
print("Appel LLM : non")
print(
    "Validation humaine requise :",
    "non",
)
print("Journal vivant écrit : non")
