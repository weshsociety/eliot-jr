import copy
import unittest
from datetime import datetime, timezone

from core.memory_accessibility import (
    MemoryAccessibilityError,
    build_memory_accessibility_snapshot,
    validate_memory_accessibility_snapshot,
)


NOW = datetime(
    2026,
    8,
    20,
    14,
    0,
    0,
    tzinfo=timezone.utc,
)


class MemoryAccessibilityTests(unittest.TestCase):
    def _snapshot(self):
        return build_memory_accessibility_snapshot(
            memory_ref="memory:test:001",
            archive_ref="archive:test",
            encounter_count=4,
            reactivation_count=2,
            currently_reactivated=False,
            last_encountered_at_utc=(
                "2026-08-20T13:00:00Z"
            ),
            last_reactivated_at_utc=(
                "2026-08-19T14:00:00Z"
            ),
            active_context_refs=[
                "context:test",
            ],
            reactivation_trigger_refs=[
                "event:test",
            ],
            now=NOW,
        )

    def test_snapshot_preserves_archive(self):
        snapshot = self._snapshot()

        self.assertTrue(
            snapshot["archive_retained"]
        )
        self.assertFalse(
            snapshot["forgetting_applied"]
        )
        self.assertFalse(
            snapshot["archive_mutation_applied"]
        )

    def test_elapsed_time_is_observed_without_decay(self):
        snapshot = self._snapshot()

        self.assertEqual(
            snapshot[
                "elapsed_since_last_encounter_seconds"
            ],
            3600,
        )
        self.assertEqual(
            snapshot[
                "elapsed_since_last_reactivation_seconds"
            ],
            86400,
        )
        self.assertFalse(
            snapshot["salience_score_assigned"]
        )

    def test_old_memory_remains_valid(self):
        snapshot = (
            build_memory_accessibility_snapshot(
                memory_ref="memory:old",
                archive_ref="archive:test",
                encounter_count=1,
                reactivation_count=1,
                currently_reactivated=False,
                last_encountered_at_utc=(
                    "2020-01-01T00:00:00Z"
                ),
                last_reactivated_at_utc=(
                    "2020-01-01T00:00:00Z"
                ),
                now=NOW,
            )
        )

        self.assertTrue(
            snapshot["archive_retained"]
        )
        self.assertFalse(
            snapshot["forgetting_applied"]
        )

    def test_reactivated_memory_needs_reactivation_history(self):
        with self.assertRaises(
            MemoryAccessibilityError
        ):
            build_memory_accessibility_snapshot(
                memory_ref="memory:test",
                archive_ref="archive:test",
                encounter_count=1,
                reactivation_count=0,
                currently_reactivated=True,
                now=NOW,
            )

    def test_reactivation_cannot_exceed_encounters(self):
        with self.assertRaises(
            MemoryAccessibilityError
        ):
            build_memory_accessibility_snapshot(
                memory_ref="memory:test",
                archive_ref="archive:test",
                encounter_count=1,
                reactivation_count=2,
                currently_reactivated=False,
                now=NOW,
            )

    def test_inputs_are_not_mutated(self):
        contexts = [
            "context:one",
            "context:two",
        ]
        triggers = [
            "event:one",
        ]

        expected_contexts = copy.deepcopy(
            contexts
        )
        expected_triggers = copy.deepcopy(
            triggers
        )

        build_memory_accessibility_snapshot(
            memory_ref="memory:test",
            archive_ref="archive:test",
            encounter_count=1,
            reactivation_count=0,
            currently_reactivated=False,
            active_context_refs=contexts,
            reactivation_trigger_refs=triggers,
            now=NOW,
        )

        self.assertEqual(
            contexts,
            expected_contexts,
        )
        self.assertEqual(
            triggers,
            expected_triggers,
        )

    def test_tampering_is_rejected(self):
        snapshot = self._snapshot()

        snapshot["encounter_count"] = 999

        with self.assertRaises(
            MemoryAccessibilityError
        ):
            validate_memory_accessibility_snapshot(
                snapshot
            )

    def test_importance_is_not_inferred(self):
        snapshot = self._snapshot()

        self.assertFalse(
            snapshot["importance_claimed"]
        )
        self.assertFalse(
            snapshot["subjective_state_claimed"]
        )
        self.assertNotIn(
            "importance_score",
            snapshot,
        )


if __name__ == "__main__":
    unittest.main()
