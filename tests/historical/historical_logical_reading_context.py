from __future__ import annotations

from pathlib import Path
import hashlib
import json
import shutil
import tempfile

from core.logical_reading_context import (
    FORBIDDEN_OUTPUT_KEYS,
    LogicalReadingContextError,
    build_logical_reading_context,
)
from core.reading_source import (
    build_reading_manifest,
)


ROOT = Path("/home/eliot-jr")

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

SOURCE = ROOT / SOURCE_RELATIVE
JOURNAL = ROOT / JOURNAL_RELATIVE

POISON = (
    "POISON_EXTERNAL_NOTE_MUST_NEVER_LEAK_"
    "7e9e817d"
)


def digest(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def recursive_keys(
    value,
) -> set[str]:
    keys = set()

    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(key)
            keys.update(
                recursive_keys(child)
            )

    elif isinstance(value, list):
        for child in value:
            keys.update(
                recursive_keys(child)
            )

    return keys


live_before = {
    str(SOURCE): digest(SOURCE),
    str(JOURNAL): digest(JOURNAL),
}

manifest, warnings = build_reading_manifest(
    ROOT,
    SOURCE_RELATIVE,
)

assert manifest["passage_count"] == 21
assert manifest["source_sha256"] == (
    live_before[str(SOURCE)]
)
assert warnings == []

contexts = {}

for passage_number in range(1, 5):
    passage_id = (
        f"passage_{passage_number:04d}"
    )

    first = build_logical_reading_context(
        project_root=ROOT,
        journal_id=JOURNAL_ID,
        passage_id=passage_id,
    )

    second = build_logical_reading_context(
        project_root=ROOT,
        journal_id=JOURNAL_ID,
        passage_id=passage_id,
    )

    assert first == second
    assert first["context_sha256"] == (
        second["context_sha256"]
    )
    assert first["llm_used"] is False
    assert (
        first["processing_mode"]
        == "deterministic_non_llm"
    )
    assert (
        first["passage"]["passage_id"]
        == passage_id
    )
    assert (
        first["passage"]["queue_status"]
        == "encountered"
    )
    assert (
        first["source"][
            "source_declares_partial_corpus"
        ]
        is True
    )
    assert (
        first["source"]["passage_count"]
        == 21
    )
    assert (
        first["access_manifest"][
            "external_note_content_exposed"
        ]
        is False
    )
    assert (
        first["access_manifest"][
            "collective_review_content_exposed"
        ]
        is False
    )

    output_keys = recursive_keys(first)

    assert not (
        output_keys
        & FORBIDDEN_OUTPUT_KEYS
    )

    serialised = json.dumps(
        first,
        ensure_ascii=False,
        sort_keys=True,
    )

    assert POISON not in serialised

    contexts[passage_id] = first


try:
    build_logical_reading_context(
        project_root=ROOT,
        journal_id=JOURNAL_ID,
        passage_id="passage_0005",
    )
except LogicalReadingContextError as error:
    queued_error = str(error)
else:
    raise AssertionError(
        "passage_0005 aurait dû être refusé."
    )


with tempfile.TemporaryDirectory() as temp:
    temp_root = Path(temp)

    temp_source = (
        temp_root / SOURCE_RELATIVE
    )
    temp_journal = (
        temp_root / JOURNAL_RELATIVE
    )

    temp_source.parent.mkdir(
        parents=True,
        exist_ok=True,
        mode=0o700,
    )
    temp_journal.parent.mkdir(
        parents=True,
        exist_ok=True,
        mode=0o700,
    )

    shutil.copy2(
        SOURCE,
        temp_source,
    )
    shutil.copy2(
        JOURNAL,
        temp_journal,
    )

    journal = json.loads(
        temp_journal.read_text(
            encoding="utf-8"
        )
    )

    for encounter in journal[
        "encounters"
    ]:
        encounter[
            "external_reading_note"
        ]["provisional_understanding"] = (
            POISON
        )
        encounter[
            "collective_review"
        ]["text"] = POISON

    temp_journal.write_text(
        json.dumps(
            journal,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    poisoned_context = (
        build_logical_reading_context(
            project_root=temp_root,
            journal_id=JOURNAL_ID,
            passage_id="passage_0004",
        )
    )

    poisoned_serialised = json.dumps(
        poisoned_context,
        ensure_ascii=False,
        sort_keys=True,
    )

    assert POISON not in poisoned_serialised
    assert not (
        recursive_keys(poisoned_context)
        & FORBIDDEN_OUTPUT_KEYS
    )


live_after = {
    str(SOURCE): digest(SOURCE),
    str(JOURNAL): digest(JOURNAL),
}

assert live_before == live_after

print(
    "===== SAS LOGIQUE DÉTERMINISTE ====="
)
print(
    "Passages reconstruits :",
    manifest["passage_count"],
)
print(
    "Contextes stables :",
    len(contexts),
)
print(
    "Corpus déclaré partiel :",
    contexts["passage_0001"][
        "source"
    ][
        "source_declares_partial_corpus"
    ],
)
print(
    "Passage 0005 refusé :",
    queued_error,
)
print(
    "Poison externe absent :",
    POISON not in poisoned_serialised,
)
print(
    "Clés interdites absentes :",
    not (
        recursive_keys(poisoned_context)
        & FORBIDDEN_OUTPUT_KEYS
    ),
)
print(
    "États vivants inchangés :",
    live_before == live_after,
)
print("Appel LLM : non")
print("Écriture journal : non")
print("Apprentissage produit : non")
