import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.body_history import (
    BodyHistoryError,
    build_empty_body_history,
    commit_body_transformation_append,
    load_body_history,
    preview_body_transformation_append,
    validate_body_history,
)
from core.body_schema import (
    build_body_snapshot,
    build_body_transformation,
)


NOW = datetime(
    2026,
    8,
    20,
    12,
    0,
    0,
    tzinfo=timezone.utc,
)


class BodyHistoryTests(unittest.TestCase):
    def _snapshot(
        self,
        memory_id: str,
        second: int,
    ):
        return build_body_snapshot(
            functional_state={
                "active_memory": memory_id,
                "active_commitment": "commitment_001",
            },
            component_refs={
                "memory": "memory_state:test",
                "will": "will_state:test",
            },
            now=NOW + timedelta(seconds=second),
        )

    def _transformation(
        self,
        *,
        event_ref: str,
        before,
        after,
        second: int,
    ):
        return build_body_transformation(
            event_ref=event_ref,
            state_before=before,
            state_after=after,
            observed_changes=[
                "active_memory changed",
            ],
            persistent_changes=[],
            reactivated_memories=[
                after["functional_state"][
                    "active_memory"
                ]
            ],
            affected_patterns=[],
            interpretations=[],
            now=NOW + timedelta(seconds=second),
        )

    def test_empty_history_is_valid(self):
        history = build_empty_body_history(
            now=NOW
        )

        self.assertEqual(
            history["entry_count"],
            0,
        )
        self.assertEqual(
            history["entries"],
            [],
        )
        self.assertTrue(
            history["append_only"]
        )
        self.assertFalse(
            history["subjective_state_claimed"]
        )

    def test_preview_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "body_history.json"

            before = self._snapshot(
                "memory_001",
                1,
            )
            after = self._snapshot(
                "memory_002",
                2,
            )

            transformation = self._transformation(
                event_ref="interaction:test:001",
                before=before,
                after=after,
                second=3,
            )

            report = (
                preview_body_transformation_append(
                    path,
                    transformation,
                    now=NOW + timedelta(seconds=4),
                )
            )

            self.assertEqual(
                report["status"],
                "append_ready",
            )
            self.assertFalse(
                report[
                    "registry_mutation_applied"
                ]
            )
            self.assertFalse(
                path.exists()
            )

    def test_commit_creates_verified_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "body_history.json"

            before = self._snapshot(
                "memory_001",
                1,
            )
            after = self._snapshot(
                "memory_002",
                2,
            )

            transformation = self._transformation(
                event_ref="interaction:test:002",
                before=before,
                after=after,
                second=3,
            )

            report = (
                commit_body_transformation_append(
                    path,
                    transformation,
                    now=NOW + timedelta(seconds=4),
                )
            )

            self.assertEqual(
                report["status"],
                "committed",
            )
            self.assertTrue(
                report[
                    "registry_mutation_applied"
                ]
            )
            self.assertTrue(
                path.exists()
            )

            history = load_body_history(path)

            self.assertEqual(
                history["entry_count"],
                1,
            )

    def test_second_entry_is_cryptographically_chained(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "body_history.json"

            first_before = self._snapshot(
                "memory_001",
                1,
            )
            first_after = self._snapshot(
                "memory_002",
                2,
            )

            first = self._transformation(
                event_ref="interaction:test:003",
                before=first_before,
                after=first_after,
                second=3,
            )

            commit_body_transformation_append(
                path,
                first,
                now=NOW + timedelta(seconds=4),
            )

            second_after = self._snapshot(
                "memory_003",
                5,
            )

            second = self._transformation(
                event_ref="interaction:test:004",
                before=first_after,
                after=second_after,
                second=6,
            )

            commit_body_transformation_append(
                path,
                second,
                now=NOW + timedelta(seconds=7),
            )

            history = load_body_history(path)

            self.assertEqual(
                history["entry_count"],
                2,
            )
            self.assertEqual(
                history["entries"][1][
                    "previous_entry_sha256"
                ],
                history["entries"][0][
                    "entry_sha256"
                ],
            )

    def test_discontinuity_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "body_history.json"

            first_before = self._snapshot(
                "memory_001",
                1,
            )
            first_after = self._snapshot(
                "memory_002",
                2,
            )

            first = self._transformation(
                event_ref="interaction:test:005",
                before=first_before,
                after=first_after,
                second=3,
            )

            commit_body_transformation_append(
                path,
                first,
                now=NOW + timedelta(seconds=4),
            )

            wrong_before = self._snapshot(
                "memory_999",
                5,
            )
            second_after = self._snapshot(
                "memory_003",
                6,
            )

            second = self._transformation(
                event_ref="interaction:test:006",
                before=wrong_before,
                after=second_after,
                second=7,
            )

            with self.assertRaises(
                BodyHistoryError
            ):
                preview_body_transformation_append(
                    path,
                    second,
                    now=NOW + timedelta(seconds=8),
                )

    def test_duplicate_commit_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "body_history.json"

            before = self._snapshot(
                "memory_001",
                1,
            )
            after = self._snapshot(
                "memory_002",
                2,
            )

            transformation = self._transformation(
                event_ref="interaction:test:007",
                before=before,
                after=after,
                second=3,
            )

            commit_body_transformation_append(
                path,
                transformation,
                now=NOW + timedelta(seconds=4),
            )

            before_bytes = path.read_bytes()

            second_report = (
                commit_body_transformation_append(
                    path,
                    transformation,
                    now=NOW + timedelta(seconds=9),
                )
            )

            after_bytes = path.read_bytes()

            self.assertEqual(
                second_report["status"],
                "already_recorded",
            )
            self.assertFalse(
                second_report[
                    "registry_mutation_applied"
                ]
            )
            self.assertEqual(
                before_bytes,
                after_bytes,
            )

    def test_tampered_history_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "body_history.json"

            before = self._snapshot(
                "memory_001",
                1,
            )
            after = self._snapshot(
                "memory_002",
                2,
            )

            transformation = self._transformation(
                event_ref="interaction:test:008",
                before=before,
                after=after,
                second=3,
            )

            commit_body_transformation_append(
                path,
                transformation,
                now=NOW + timedelta(seconds=4),
            )

            payload = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )

            payload["entries"][0][
                "transformation"
            ]["event_ref"] = "interaction:tampered"

            path.write_text(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            with self.assertRaises(
                BodyHistoryError
            ):
                load_body_history(path)

    def test_validator_rejects_broken_chain(self):
        history = build_empty_body_history(
            now=NOW
        )

        history["entries"] = [
            {
                "sequence": 1,
                "entry_id": "fake",
                "recorded_at_utc": (
                    "2026-08-20T12:00:00Z"
                ),
                "previous_entry_sha256": "wrong",
                "transformation": {},
                "body_state_mutation_applied": False,
                "subjective_state_claimed": False,
                "external_action_performed": False,
                "entry_sha256": "fake",
            }
        ]
        history["entry_count"] = 1

        with self.assertRaises(
            BodyHistoryError
        ):
            validate_body_history(history)


if __name__ == "__main__":
    unittest.main()
