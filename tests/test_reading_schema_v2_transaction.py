from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import shutil
import tempfile

from core.reading_schema_v2_transaction import (
    ReadingSchemaV2TransactionError,
    apply_reading_schema_v2,
)


ROOT = Path("/home/eliot-jr")

LIVE_JOURNAL = (
    ROOT
    / "curriculum"
    / "journaux"
    / "lecture_thoreau_desobeissance_civile.json"
)

LIVE_CANDIDATES = (
    ROOT
    / ".memory"
    / "reading_candidates"
)


def digest(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def copy_reading_state(
    target: Path,
) -> None:
    journal_target = (
        target
        / "curriculum"
        / "journaux"
        / LIVE_JOURNAL.name
    )

    candidates_target = (
        target
        / ".memory"
        / "reading_candidates"
    )

    journal_target.parent.mkdir(
        parents=True,
        exist_ok=True,
        mode=0o700,
    )

    candidates_target.mkdir(
        parents=True,
        exist_ok=True,
        mode=0o700,
    )

    shutil.copy2(
        LIVE_JOURNAL,
        journal_target,
    )

    for path in sorted(
        LIVE_CANDIDATES.glob("*.json")
    ):
        shutil.copy2(
            path,
            candidates_target / path.name,
        )


def state_hashes(
    root: Path,
) -> dict[str, str]:
    candidates_root = (
        root
        / ".memory"
        / "reading_candidates"
    )

    paths = [
        (
            root
            / "curriculum"
            / "journaux"
            / LIVE_JOURNAL.name
        ),
        *sorted(
            candidates_root.glob("*.json")
        ),
    ]

    return {
        str(path.relative_to(root)): digest(path)
        for path in paths
    }


live_paths = [
    LIVE_JOURNAL,
    *sorted(
        LIVE_CANDIDATES.glob("*.json")
    ),
]

live_before = {
    str(path): digest(path)
    for path in live_paths
}

FIXED_TIME = datetime(
    2026,
    7,
    29,
    10,
    0,
    tzinfo=timezone.utc,
)


with tempfile.TemporaryDirectory() as temp:
    copy_root = Path(temp) / "success"
    copy_reading_state(copy_root)

    first = apply_reading_schema_v2(
        project_root=copy_root,
        now=FIXED_TIME,
    )

    hashes_after_first = state_hashes(
        copy_root
    )

    second = apply_reading_schema_v2(
        project_root=copy_root,
        now=FIXED_TIME,
    )

    hashes_after_second = state_hashes(
        copy_root
    )

    journal_path = (
        copy_root
        / "curriculum"
        / "journaux"
        / LIVE_JOURNAL.name
    )

    journal = json.loads(
        journal_path.read_text(
            encoding="utf-8"
        )
    )

    passage_0005 = next(
        item
        for item in journal["reading_queue"]
        if item.get("passage_id")
        == "passage_0005"
    )

    print("===== MIGRATION SUR COPIE =====")
    print(
        "Migration appliquée :",
        first["migrated"],
    )
    print(
        "Documents écrits :",
        first["documents_written"],
    )
    print(
        "Candidates écrites :",
        first[
            "candidate_documents_written"
        ],
    )
    print(
        "Journal écrit :",
        first["journal_written"],
    )
    print(
        "Schéma journal :",
        first["status"][
            "journal_schema_version"
        ],
    )
    print(
        "Notes externes :",
        first["status"][
            "external_reading_note_count"
        ],
    )
    print(
        "Revues collectives :",
        first["status"][
            "collective_review_count"
        ],
    )
    print(
        "Apprentissages logiques :",
        first["status"][
            "logical_learning_count"
        ],
    )
    print(
        "Apprentissages en attente :",
        first["status"][
            "logical_learning_pending_count"
        ],
    )
    print(
        "Passage 0005 :",
        passage_0005["status"],
    )
    print(
        "Sauvegarde préalable :",
        first["pre_backup"]["verified"],
    )
    print(
        "Sauvegarde postérieure :",
        first["post_backup"]["verified"],
    )

    print("\n===== IDEMPOTENCE =====")
    print(
        "Deuxième appel déjà appliqué :",
        second["already_applied"],
    )
    print(
        "Documents réécrits :",
        second["documents_written"],
    )
    print(
        "Octets inchangés :",
        hashes_after_first
        == hashes_after_second,
    )

    assert first["migrated"] is True
    assert first["documents_written"] == 5
    assert (
        first["candidate_documents_written"]
        == 4
    )
    assert first["journal_written"] is True
    assert (
        first["status"][
            "journal_schema_version"
        ]
        == 2
    )
    assert (
        first["status"][
            "external_reading_note_count"
        ]
        == 4
    )
    assert (
        first["status"][
            "collective_review_count"
        ]
        == 4
    )
    assert (
        first["status"][
            "logical_learning_count"
        ]
        == 0
    )
    assert (
        first["status"][
            "logical_learning_pending_count"
        ]
        == 4
    )
    assert passage_0005["status"] == "queued"
    assert second["already_applied"] is True
    assert second["documents_written"] == 0
    assert hashes_after_first == hashes_after_second


with tempfile.TemporaryDirectory() as temp:
    rollback_root = (
        Path(temp) / "rollback"
    )

    copy_reading_state(
        rollback_root
    )

    before_failure = state_hashes(
        rollback_root
    )

    try:
        apply_reading_schema_v2(
            project_root=rollback_root,
            now=FIXED_TIME,
            fault_after_write_count=2,
        )
    except ReadingSchemaV2TransactionError as error:
        print("\n===== PANNE ARTIFICIELLE =====")
        print("Erreur capturée :", error)
    else:
        raise AssertionError(
            "La panne artificielle "
            "n’a pas été déclenchée."
        )

    after_failure = state_hashes(
        rollback_root
    )

    restored_journal_path = (
        rollback_root
        / "curriculum"
        / "journaux"
        / LIVE_JOURNAL.name
    )

    restored_journal = json.loads(
        restored_journal_path.read_text(
            encoding="utf-8"
        )
    )

    print(
        "Restauration exacte :",
        before_failure == after_failure,
    )
    print(
        "Schéma après restauration :",
        restored_journal.get(
            "schema_version",
            1,
        ),
    )

    assert before_failure == after_failure
    assert (
        restored_journal.get(
            "schema_version",
            1,
        )
        == 1
    )


live_after = {
    str(path): digest(path)
    for path in live_paths
}


print("\n===== GARANTIES VIVANTES =====")
print(
    "États vivants inchangés :",
    live_before == live_after,
)
print("Migration testée sur copie : oui")
print("Restauration testée         : oui")
print("Appel LLM                   : non")
print("Passage 0005 traité         : non")

assert live_before == live_after
