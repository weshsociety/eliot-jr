from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import shutil
import tempfile

import core.logical_learning_registry as registry
from core.logical_learning_registry import (
    LogicalLearningRegistryError,
    record_logical_learning,
)
from core.logical_reading_context import (
    build_logical_reading_context,
)
from core.logical_surface_analysis import (
    analyse_logical_surface,
)


LIVE_ROOT = Path("/home/eliot-jr")

JOURNAL_ID = (
    "lecture_thoreau_desobeissance_civile"
)

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

POISON = (
    "POISON_EXTERNAL_NOTE_MUST_NOT_ENTER_"
    "LOGICAL_LEARNING_4d0bbad9"
)


def digest(
    path: Path,
) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def live_hashes() -> dict[str, str]:
    source = (
        LIVE_ROOT / SOURCE_RELATIVE
    )
    journal = (
        LIVE_ROOT / JOURNAL_RELATIVE
    )
    candidates = (
        LIVE_ROOT
        / CANDIDATES_RELATIVE
    )

    paths = [
        source,
        journal,
        *sorted(
            candidates.glob("*.json")
        ),
    ]

    return {
        str(path): digest(path)
        for path in paths
    }


def canonical_hash(
    value,
) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    return hashlib.sha256(
        payload
    ).hexdigest()


def revised_analysis(
    analysis: dict,
) -> dict:
    revised = deepcopy(analysis)
    revised.pop(
        "analysis_sha256",
        None,
    )
    revised.pop(
        "analysis_id",
        None,
    )

    revised[
        "synthetic_test_revision"
    ] = {
        "purpose": (
            "verify_revision_preservation"
        ),
        "llm_used": False,
    }

    analysis_hash = canonical_hash(
        revised
    )
    passage_id = revised[
        "passage_identity"
    ]["passage_id"]

    revised["analysis_sha256"] = (
        analysis_hash
    )
    revised["analysis_id"] = (
        f"{passage_id}:"
        f"{analysis_hash[:16]}"
    )

    return revised


def setup_temp_root(
    destination: Path,
) -> None:
    source_target = (
        destination / SOURCE_RELATIVE
    )
    journal_target = (
        destination / JOURNAL_RELATIVE
    )
    candidates_target = (
        destination
        / CANDIDATES_RELATIVE
    )

    source_target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    journal_target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    candidates_target.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        LIVE_ROOT / SOURCE_RELATIVE,
        source_target,
    )
    shutil.copy2(
        LIVE_ROOT / JOURNAL_RELATIVE,
        journal_target,
    )

    live_candidates = (
        LIVE_ROOT
        / CANDIDATES_RELATIVE
    )

    for candidate in live_candidates.glob(
        "*.json"
    ):
        shutil.copy2(
            candidate,
            candidates_target
            / candidate.name,
        )


def poison_external_layers(
    root: Path,
) -> None:
    path = root / JOURNAL_RELATIVE

    journal = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    for encounter in journal[
        "encounters"
    ]:
        if isinstance(
            encounter.get(
                "external_reading_note"
            ),
            dict,
        ):
            encounter[
                "external_reading_note"
            ][
                "logical_registry_poison"
            ] = POISON

        if isinstance(
            encounter.get(
                "collective_review"
            ),
            dict,
        ):
            encounter[
                "collective_review"
            ][
                "logical_registry_poison"
            ] = POISON

    path.write_text(
        json.dumps(
            journal,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


live_before = live_hashes()

with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    setup_temp_root(root)
    poison_external_layers(root)

    journal_path = (
        root / JOURNAL_RELATIVE
    )
    backup_root = (
        root
        / ".backups"
        / "reading"
    )

    journal_before = json.loads(
        journal_path.read_text(
            encoding="utf-8"
        )
    )

    context = (
        build_logical_reading_context(
            project_root=root,
            journal_id=JOURNAL_ID,
            passage_id="passage_0001",
        )
    )
    analysis = (
        analyse_logical_surface(
            context
        )
    )

    persisted, report = (
        record_logical_learning(
            project_root=root,
            journal_id=JOURNAL_ID,
            context=context,
            analysis=analysis,
            now=datetime(
                2026,
                7,
                29,
                12,
                0,
                tzinfo=timezone.utc,
            ),
            commit=True,
            backup_root=backup_root,
        )
    )

    assert report["committed"] is True
    assert (
        report["already_recorded"]
        is False
    )
    assert report["llm_used"] is False
    assert (
        report[
            "human_approval_required"
        ]
        is False
    )

    encounter = next(
        item
        for item in persisted[
            "encounters"
        ]
        if item.get("passage_id")
        == "passage_0001"
    )

    learning = encounter[
        "eliot_learning_state"
    ]

    assert learning["status"] == "processed"
    assert (
        learning["producer"]
        == "eliot_jr_logical_core"
    )
    assert learning["llm_used"] is False
    assert (
        learning[
            "human_approval_required_to_exist"
        ]
        is False
    )
    assert learning["terms"]
    assert learning["claims"]
    assert learning["questions"]
    assert learning["revisions"] == []
    assert POISON not in json.dumps(
        learning,
        ensure_ascii=False,
        sort_keys=True,
    )

    queue_item = next(
        item
        for item in persisted[
            "reading_queue"
        ]
        if item.get("passage_id")
        == "passage_0001"
    )

    assert (
        queue_item[
            "eliot_learning_status"
        ]
        == "processed"
    )

    encounter_before = next(
        item
        for item in journal_before[
            "encounters"
        ]
        if item.get("passage_id")
        == "passage_0001"
    )

    assert (
        encounter_before[
            "external_reading_note"
        ]
        == encounter[
            "external_reading_note"
        ]
    )
    assert (
        encounter_before[
            "collective_review"
        ]
        == encounter[
            "collective_review"
        ]
    )

    manifests_after_first = sorted(
        backup_root.glob(
            "*.manifest.json"
        )
    )

    assert len(
        manifests_after_first
    ) == 2

    first_bytes = (
        journal_path.read_bytes()
    )

    second_persisted, second_report = (
        record_logical_learning(
            project_root=root,
            journal_id=JOURNAL_ID,
            context=context,
            analysis=analysis,
            now=datetime(
                2026,
                7,
                29,
                13,
                0,
                tzinfo=timezone.utc,
            ),
            commit=True,
            backup_root=backup_root,
        )
    )

    assert (
        second_report[
            "already_recorded"
        ]
        is True
    )
    assert (
        second_report["committed"]
        is False
    )
    assert (
        journal_path.read_bytes()
        == first_bytes
    )
    assert (
        len(
            list(
                backup_root.glob(
                    "*.manifest.json"
                )
            )
        )
        == 2
    )
    assert second_persisted == persisted

    revised = revised_analysis(
        analysis
    )

    revised_persisted, revised_report = (
        record_logical_learning(
            project_root=root,
            journal_id=JOURNAL_ID,
            context=context,
            analysis=revised,
            now=datetime(
                2026,
                7,
                29,
                14,
                0,
                tzinfo=timezone.utc,
            ),
            commit=True,
            backup_root=backup_root,
        )
    )

    assert (
        revised_report["event"]
        == "logical_learning_revised"
    )

    revised_encounter = next(
        item
        for item in revised_persisted[
            "encounters"
        ]
        if item.get("passage_id")
        == "passage_0001"
    )

    revised_learning = (
        revised_encounter[
            "eliot_learning_state"
        ]
    )

    assert len(
        revised_learning[
            "revisions"
        ]
    ) == 1

    previous = revised_learning[
        "revisions"
    ][0]["previous_state"]

    assert (
        previous["analysis_sha256"]
        == analysis[
            "analysis_sha256"
        ]
    )
    assert (
        previous[
            "learning_state_sha256"
        ]
        == learning[
            "learning_state_sha256"
        ]
    )

    preview_context = (
        build_logical_reading_context(
            project_root=root,
            journal_id=JOURNAL_ID,
            passage_id="passage_0002",
        )
    )
    preview_analysis = (
        analyse_logical_surface(
            preview_context
        )
    )

    preview_before = (
        journal_path.read_bytes()
    )

    preview_document, preview_report = (
        record_logical_learning(
            project_root=root,
            journal_id=JOURNAL_ID,
            context=preview_context,
            analysis=preview_analysis,
            now=datetime(
                2026,
                7,
                29,
                15,
                0,
                tzinfo=timezone.utc,
            ),
            commit=False,
            backup_root=backup_root,
        )
    )

    assert (
        preview_report["committed"]
        is False
    )
    assert (
        preview_report[
            "already_recorded"
        ]
        is False
    )
    assert (
        journal_path.read_bytes()
        == preview_before
    )

    preview_encounter = next(
        item
        for item in preview_document[
            "encounters"
        ]
        if item.get("passage_id")
        == "passage_0002"
    )

    assert (
        preview_encounter[
            "eliot_learning_state"
        ]["status"]
        == "processed"
    )

    bad_analysis = deepcopy(
        preview_analysis
    )
    bad_analysis[
        "analysis_sha256"
    ] = "0" * 64

    try:
        record_logical_learning(
            project_root=root,
            journal_id=JOURNAL_ID,
            context=preview_context,
            analysis=bad_analysis,
            commit=False,
            backup_root=backup_root,
        )
    except LogicalLearningRegistryError as error:
        bad_hash_error = str(error)
    else:
        raise AssertionError(
            "Une mauvaise empreinte "
            "d’analyse a été acceptée."
        )

    rollback_before = (
        journal_path.read_bytes()
    )

    real_backup = (
        registry.create_backup
    )
    calls = {"count": 0}

    def failing_second_backup(
        **kwargs,
    ):
        calls["count"] += 1

        if calls["count"] == 2:
            raise RuntimeError(
                "artificial_post_backup_failure"
            )

        return real_backup(**kwargs)

    registry.create_backup = (
        failing_second_backup
    )

    try:
        record_logical_learning(
            project_root=root,
            journal_id=JOURNAL_ID,
            context=preview_context,
            analysis=preview_analysis,
            now=datetime(
                2026,
                7,
                29,
                16,
                0,
                tzinfo=timezone.utc,
            ),
            commit=True,
            backup_root=backup_root,
        )
    except LogicalLearningRegistryError as error:
        rollback_error = str(error)
    else:
        raise AssertionError(
            "L’échec artificiel aurait "
            "dû annuler la transaction."
        )
    finally:
        registry.create_backup = (
            real_backup
        )

    assert (
        journal_path.read_bytes()
        == rollback_before
    )


live_after = live_hashes()

assert live_before == live_after

print(
    "===== REGISTRE D’APPRENTISSAGE LOGIQUE ====="
)
print(
    "Premier apprentissage :",
    report["event"],
)
print(
    "Idempotence :",
    second_report["event"],
)
print(
    "Révision conservée :",
    len(
        revised_learning[
            "revisions"
        ]
    ),
)
print(
    "Prévisualisation sans écriture :",
    preview_report["committed"]
    is False,
)
print(
    "Mauvaise empreinte refusée :",
    bad_hash_error,
)
print(
    "Restauration après échec :",
    rollback_error,
)
print(
    "Poison externe absent :",
    POISON not in json.dumps(
        learning,
        ensure_ascii=False,
    ),
)
print(
    "États vivants inchangés :",
    live_before == live_after,
)
print("Appel LLM : non")
print("Validation humaine requise : non")
print("Journal vivant écrit : non")
