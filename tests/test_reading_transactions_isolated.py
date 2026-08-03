from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import shutil
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


PROJECT_ROOT = Path(__file__).resolve().parents[1]
JOURNAL_ID = "lecture_thoreau_desobeissance_civile"
JOURNAL_RELATIVE = Path(
    "curriculum/journaux/lecture_thoreau_desobeissance_civile.json"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def _copy_and_rewind_tail(
    destination: Path,
    *,
    remove_count: int,
) -> tuple[list[str], dict[str, str]]:
    live_journal_path = PROJECT_ROOT / JOURNAL_RELATIVE
    journal = json.loads(live_journal_path.read_text(encoding="utf-8"))

    if journal.get("schema_version") != 2:
        raise AssertionError("Le journal vivant doit être en schéma v2.")

    encounters = journal.get("encounters")
    queue = journal.get("reading_queue")

    if not isinstance(encounters, list) or len(encounters) < remove_count + 1:
        raise AssertionError("Pas assez de rencontres pour la fixture isolée.")
    if not isinstance(queue, list):
        raise AssertionError("File de lecture invalide.")

    source_relative = Path(journal["work"]["source_file"])
    source_live = PROJECT_ROOT / source_relative
    source_target = destination / source_relative
    journal_target = destination / JOURNAL_RELATIVE

    source_target.parent.mkdir(parents=True, exist_ok=True)
    journal_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_live, source_target)

    removed = encounters[-remove_count:]
    removed_ids = [str(item["passage_id"]) for item in removed]
    journal["encounters"] = encounters[:-remove_count]
    journal["encounter_count"] = len(journal["encounters"])

    transient_queue_keys = {
        "exposed_at_utc",
        "encounter_id",
        "encounter_number",
        "encounter_sha256",
        "encounter_registry",
        "eliot_learning_processed_at_utc",
        "eliot_learning_analysis_sha256",
        "eliot_learning_content_sha256",
        "eliot_learning_state_sha256",
    }

    for item in queue:
        if item.get("passage_id") not in removed_ids:
            continue
        item["status"] = "queued"
        item["eliot_learning_status"] = "not_yet_processed"
        for key in transient_queue_keys:
            item.pop(key, None)

    history = journal.get("change_history", [])
    if isinstance(history, list):
        journal["change_history"] = [
            item
            for item in history
            if not (
                isinstance(item, dict)
                and item.get("passage_id") in removed_ids
                and item.get("event")
                in {
                    "reading_encounter_recorded",
                    "logical_learning_recorded",
                    "logical_learning_revised",
                }
            )
        ]

    journal_target.write_text(
        json.dumps(journal, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    live_hashes = {
        "journal": _sha256(live_journal_path),
        "source": _sha256(source_live),
    }
    return removed_ids, live_hashes


class IsolatedReadingTransactionTests(unittest.TestCase):
    def _assert_live_unchanged(self, hashes: dict[str, str]) -> None:
        journal_path = PROJECT_ROOT / JOURNAL_RELATIVE
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        source_path = PROJECT_ROOT / Path(journal["work"]["source_file"])
        self.assertEqual(_sha256(journal_path), hashes["journal"])
        self.assertEqual(_sha256(source_path), hashes["source"])

    def test_encounter_order_preview_commit_and_idempotence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="eliot-encounter-test-") as temp:
            root = Path(temp)
            passage_ids, live_hashes = _copy_and_rewind_tail(
                root,
                remove_count=2,
            )
            first_id, second_id = passage_ids
            journal_path = root / JOURNAL_RELATIVE
            before = journal_path.read_bytes()
            backup_root = root / ".backups" / "reading"

            with self.assertRaises(ReadingEncounterRegistryError):
                record_reading_encounter(
                    project_root=root,
                    journal_id=JOURNAL_ID,
                    passage_id=second_id,
                    now=datetime(2030, 1, 1, tzinfo=timezone.utc),
                    commit=False,
                    backup_root=backup_root,
                )

            preview, preview_report = record_reading_encounter(
                project_root=root,
                journal_id=JOURNAL_ID,
                passage_id=first_id,
                now=datetime(2030, 1, 1, 0, 1, tzinfo=timezone.utc),
                commit=False,
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
                backup_root=backup_root,
            )
            self.assertTrue(again_report["already_recorded"])
            self.assertFalse(again_report["committed"])
            self.assertEqual(journal_path.read_bytes(), committed_bytes)
            self.assertEqual(again["encounter_count"], persisted["encounter_count"])
            self._assert_live_unchanged(live_hashes)

    def test_context_refuses_unmet_encounter_then_is_deterministic(self) -> None:
        with tempfile.TemporaryDirectory(prefix="eliot-context-test-") as temp:
            root = Path(temp)
            passage_ids, live_hashes = _copy_and_rewind_tail(root, remove_count=1)
            passage_id = passage_ids[0]
            backup_root = root / ".backups" / "reading"

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
            self._assert_live_unchanged(live_hashes)

    def test_learning_is_idempotent_then_append_only_revised(self) -> None:
        with tempfile.TemporaryDirectory(prefix="eliot-learning-test-") as temp:
            root = Path(temp)
            passage_ids, live_hashes = _copy_and_rewind_tail(root, remove_count=1)
            passage_id = passage_ids[0]
            backup_root = root / ".backups" / "reading"

            record_reading_encounter(
                project_root=root,
                journal_id=JOURNAL_ID,
                passage_id=passage_id,
                now=datetime(2030, 1, 3, tzinfo=timezone.utc),
                commit=True,
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
            self._assert_live_unchanged(live_hashes)


if __name__ == "__main__":
    unittest.main()
