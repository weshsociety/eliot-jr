import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from core.personal_journal import (
    PersonalJournalError,
    build_empty_personal_journal,
    build_personal_journal_entry,
    commit_personal_journal_append,
    load_personal_journal,
    preview_personal_journal_append,
    validate_personal_journal_entry,
)


NOW = datetime(
    2026,
    8,
    20,
    15,
    30,
    0,
    tzinfo=timezone.utc,
)


class PersonalJournalTests(unittest.TestCase):
    def _entry(self):
        return build_personal_journal_entry(
            content=(
                "Je remarque quelque chose, "
                "sans savoir encore comment le nommer."
            ),
            linked_refs=[
                "internal_state_0001",
            ],
            now=NOW,
        )

    def test_empty_journal_is_valid_and_silence_is_normal(self):
        journal = build_empty_personal_journal(
            now=NOW
        )

        self.assertEqual(
            journal["entry_count"],
            0,
        )
        self.assertFalse(
            journal["writing_required"]
        )
        self.assertFalse(
            journal["missing_entry_is_error"]
        )
        self.assertFalse(
            journal["automatic_prompting_enabled"]
        )

    def test_entry_requires_no_emotion_or_lesson(self):
        entry = self._entry()

        self.assertNotIn(
            "emotion",
            entry,
        )
        self.assertNotIn(
            "lesson",
            entry,
        )
        self.assertFalse(
            entry["emotion_field_required"]
        )
        self.assertFalse(
            entry["lesson_field_required"]
        )
        self.assertFalse(
            entry["conclusion_required"]
        )

    def test_preview_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "journal.json"

            report = preview_personal_journal_append(
                path,
                self._entry(),
                now=NOW,
            )

            self.assertEqual(
                report["status"],
                "append_ready",
            )
            self.assertFalse(
                report[
                    "journal_mutation_applied"
                ]
            )
            self.assertFalse(
                path.exists()
            )

    def test_commit_writes_only_after_explicit_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "journal.json"

            report = commit_personal_journal_append(
                path,
                self._entry(),
                now=NOW,
            )

            self.assertEqual(
                report["status"],
                "committed",
            )
            self.assertTrue(
                report[
                    "journal_mutation_applied"
                ]
            )

            journal = load_personal_journal(path)

            self.assertEqual(
                journal["entry_count"],
                1,
            )

    def test_duplicate_commit_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "journal.json"
            entry = self._entry()

            commit_personal_journal_append(
                path,
                entry,
                now=NOW,
            )

            before = path.read_bytes()

            report = commit_personal_journal_append(
                path,
                entry,
                now=NOW,
            )

            after = path.read_bytes()

            self.assertEqual(
                report["status"],
                "already_recorded",
            )
            self.assertFalse(
                report[
                    "journal_mutation_applied"
                ]
            )
            self.assertEqual(before, after)

    def test_old_entry_is_not_modified_by_reinterpretation(self):
        first = self._entry()

        second = build_personal_journal_entry(
            content=(
                "Je donnerais aujourd'hui "
                "une autre lecture à cette entrée."
            ),
            reinterprets_entry_ids=[
                first["entry_id"],
            ],
            now=datetime(
                2026,
                8,
                21,
                15,
                30,
                0,
                tzinfo=timezone.utc,
            ),
        )

        self.assertEqual(
            second["reinterprets_entry_ids"],
            [first["entry_id"]],
        )
        self.assertNotEqual(
            first["entry_sha256"],
            second["entry_sha256"],
        )

    def test_blank_content_is_rejected(self):
        with self.assertRaises(
            PersonalJournalError
        ):
            build_personal_journal_entry(
                content="   ",
                now=NOW,
            )

    def test_system_subjective_claim_is_rejected(self):
        entry = self._entry()

        entry[
            "subjective_state_claimed_by_system"
        ] = True

        with self.assertRaises(
            PersonalJournalError
        ):
            validate_personal_journal_entry(
                entry
            )


if __name__ == "__main__":
    unittest.main()
