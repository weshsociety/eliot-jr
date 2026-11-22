from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import tempfile
import unittest

from core.logical_learning_registry import record_logical_learning
from core.logical_reading_context import (
    FORBIDDEN_OUTPUT_KEYS,
    LogicalReadingContextError,
    build_logical_reading_context,
)
from core.logical_surface_analysis import analyse_logical_surface
from core.reading_encounter_registry import (
    ReadingEncounterRegistryError,
    record_reading_encounter,
)


from core.reading_source import build_reading_manifest

JOURNAL_ID = "synthetic_reading"
JOURNAL_RELATIVE = Path(
    "curriculum/journaux/synthetic_reading.json"
)


def _canonical_hash(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _recursive_keys(value: object) -> set[str]:
    keys: set[str] = set()

    if isinstance(value, dict):
        for key, child in value.items():
            keys.add(str(key))
            keys.update(_recursive_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_recursive_keys(child))

    return keys


def _revised_analysis(analysis: dict) -> dict:
    revised = deepcopy(analysis)
    revised.pop("analysis_sha256", None)
    revised.pop("analysis_id", None)
    revised["synthetic_test_revision"] = {
        "purpose": "verify_append_only_revision",
        "llm_used": False,
    }
    digest = _canonical_hash(revised)
    passage_id = revised["passage_identity"]["passage_id"]
    revised["analysis_sha256"] = digest
    revised["analysis_id"] = f"{passage_id}:{digest[:16]}"
    return revised


def _create_reading_fixture(root: Path) -> list[str]:
    source_relative = "curriculum/sources/example.txt"
    source = root / source_relative
    source.parent.mkdir(parents=True)
    source.write_text(
        "Title: Synthetic reading fixture\n\n"
        "If the sensor is blocked, the signal stops. "
        "The sensor is blocked. Therefore the signal stops.\n\n"
        "Every measured sample is recorded. "
        "The control sample was measured.\n",
        encoding="utf-8",
    )
    manifest, _ = build_reading_manifest(root, source_relative)
    queue = [
        {
            **passage,
            "passage_sha256": passage["sha256"],
            "status": "queued",
            "eliot_learning_status": "not_yet_processed",
        }
        for passage in manifest["passages"]
    ]
    journal = root / JOURNAL_RELATIVE
    journal.parent.mkdir(parents=True)
    journal.write_text(
        json.dumps({
            "schema_version": 2,
            "journal_id": JOURNAL_ID,
            "work": {
                "source_file": source_relative,
                "source_sha256": manifest["source_sha256"],
                "source_size_bytes": manifest["source_size_bytes"],
            },
            "reading_queue": queue,
            "encounters": [],
            "encounter_count": 0,
            "change_history": [],
        }),
        encoding="utf-8",
    )
    return [passage["passage_id"] for passage in queue]


class IsolatedReadingTransactionTests(unittest.TestCase):
    def test_encounter_order_preview_commit_and_idempotence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="eliot-encounter-test-") as temp:
            root = Path(temp)
            first_id, second_id = _create_reading_fixture(root)
            journal_path = root / JOURNAL_RELATIVE
            before = journal_path.read_bytes()
            backup_root = root / ".backups" / "reading"
            memory_root = root / "private-memory"
            memory_root.mkdir(
                parents=True,
                exist_ok=True,
            )

            with self.assertRaises(ReadingEncounterRegistryError):
                record_reading_encounter(
                    project_root=root,
                    journal_id=JOURNAL_ID,
                    passage_id=second_id,
                    now=datetime(2030, 1, 1, tzinfo=timezone.utc),
                    commit=False,
                    memory_root=memory_root,
                    backup_root=backup_root,
                )

            preview, preview_report = record_reading_encounter(
                project_root=root,
                journal_id=JOURNAL_ID,
                passage_id=first_id,
                now=datetime(2030, 1, 1, 0, 1, tzinfo=timezone.utc),
                commit=False,
                memory_root=memory_root,
                backup_root=backup_root,
            )
            self.assertEqual(journal_path.read_bytes(), before)
            self.assertEqual(preview_report["event"], "reading_encounter_recorded")
            self.assertFalse(preview_report["committed"])
            self.assertFalse(preview_report["llm_used"])
            self.assertEqual(preview["encounter_count"], len(preview["encounters"]))

            persisted, report = record_reading_encounter(
                project_root=root,
                journal_id=JOURNAL_ID,
                passage_id=first_id,
                now=datetime(2030, 1, 1, 0, 2, tzinfo=timezone.utc),
                commit=True,
                memory_root=memory_root,
                backup_root=backup_root,
            )
            self.assertTrue(report["committed"])
            self.assertTrue(report["backup_created"])
            self.assertFalse(report["already_recorded"])
            self.assertEqual(persisted["encounters"][-1]["passage_id"], first_id)
            self.assertEqual(
                persisted["encounters"][-1]["eliot_learning_state"]["status"],
                "not_yet_processed",
            )

            committed_bytes = journal_path.read_bytes()
            again, again_report = record_reading_encounter(
                project_root=root,
                journal_id=JOURNAL_ID,
                passage_id=first_id,
                now=datetime(2030, 1, 1, 0, 3, tzinfo=timezone.utc),
                commit=True,
                memory_root=memory_root,
                backup_root=backup_root,
            )
            self.assertTrue(again_report["already_recorded"])
            self.assertFalse(again_report["committed"])
            self.assertEqual(journal_path.read_bytes(), committed_bytes)
            self.assertEqual(again["encounter_count"], persisted["encounter_count"])

    def test_context_refuses_unmet_encounter_then_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory(prefix="eliot-context-test-") as temp:
            root = Path(temp)
            passage_id, _ = _create_reading_fixture(root)
            backup_root = root / ".backups" / "reading"
            memory_root = root / "private-memory"
            memory_root.mkdir(
                parents=True,
                exist_ok=True,
            )

            with self.assertRaises(LogicalReadingContextError):
                build_logical_reading_context(
                    project_root=root,
                    journal_id=JOURNAL_ID,
                    passage_id=passage_id,
                )

            record_reading_encounter(
                project_root=root,
                journal_id=JOURNAL_ID,
                passage_id=passage_id,
                now=datetime(2030, 1, 2, tzinfo=timezone.utc),
                commit=True,
                memory_root=memory_root,
                backup_root=backup_root,
            )

            first = build_logical_reading_context(
                project_root=root,
                journal_id=JOURNAL_ID,
                passage_id=passage_id,
            )
            second = build_logical_reading_context(
                project_root=root,
                journal_id=JOURNAL_ID,
                passage_id=passage_id,
            )
            self.assertEqual(first, second)
            self.assertFalse(first["llm_used"])
            self.assertTrue(FORBIDDEN_OUTPUT_KEYS.isdisjoint(_recursive_keys(first)))

    def test_learning_is_idempotent_then_append_only_revised(self) -> None:
        with tempfile.TemporaryDirectory(prefix="eliot-learning-test-") as temp:
            root = Path(temp)
            passage_id, _ = _create_reading_fixture(root)
            backup_root = root / ".backups" / "reading"
            memory_root = root / "private-memory"
            memory_root.mkdir(
                parents=True,
                exist_ok=True,
            )

            record_reading_encounter(
                project_root=root,
                journal_id=JOURNAL_ID,
                passage_id=passage_id,
                now=datetime(2030, 1, 3, tzinfo=timezone.utc),
                commit=True,
                memory_root=memory_root,
                backup_root=backup_root,
            )
            context = build_logical_reading_context(
                project_root=root,
                journal_id=JOURNAL_ID,
                passage_id=passage_id,
            )
            analysis = analyse_logical_surface(context)

            persisted, report = record_logical_learning(
                project_root=root,
                journal_id=JOURNAL_ID,
                context=context,
                analysis=analysis,
                now=datetime(2030, 1, 3, 0, 1, tzinfo=timezone.utc),
                commit=True,
                memory_root=memory_root,
                backup_root=backup_root,
            )
            self.assertEqual(report["event"], "logical_learning_recorded")
            self.assertTrue(report["committed"])
            encounter = next(
                item for item in persisted["encounters"]
                if item.get("passage_id") == passage_id
            )
            first_state = encounter["eliot_learning_state"]
            self.assertEqual(first_state["status"], "processed")
            self.assertEqual(first_state["revisions"], [])
            self.assertFalse(first_state["llm_used"])

            after_first = (root / JOURNAL_RELATIVE).read_bytes()
            _, same_report = record_logical_learning(
                project_root=root,
                journal_id=JOURNAL_ID,
                context=context,
                analysis=analysis,
                now=datetime(2030, 1, 3, 0, 2, tzinfo=timezone.utc),
                commit=True,
                memory_root=memory_root,
                backup_root=backup_root,
            )
            self.assertTrue(same_report["already_recorded"])
            self.assertFalse(same_report["committed"])
            self.assertEqual((root / JOURNAL_RELATIVE).read_bytes(), after_first)

            revised = _revised_analysis(analysis)
            revised_persisted, revised_report = record_logical_learning(
                project_root=root,
                journal_id=JOURNAL_ID,
                context=context,
                analysis=revised,
                now=datetime(2030, 1, 3, 0, 3, tzinfo=timezone.utc),
                commit=True,
                memory_root=memory_root,
                backup_root=backup_root,
            )
            self.assertEqual(revised_report["event"], "logical_learning_revised")
            revised_encounter = next(
                item for item in revised_persisted["encounters"]
                if item.get("passage_id") == passage_id
            )
            revised_state = revised_encounter["eliot_learning_state"]
            self.assertEqual(len(revised_state["revisions"]), 1)
            self.assertEqual(
                revised_state["revisions"][0]["previous_analysis_sha256"],
                first_state["analysis_sha256"],
            )
            self.assertNotEqual(
                revised_state["analysis_sha256"],
                first_state["analysis_sha256"],
            )


if __name__ == "__main__":
    unittest.main()
