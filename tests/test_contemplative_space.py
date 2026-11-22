import copy
import unittest
from datetime import datetime, timezone

from core.contemplative_space import (
    ContemplativeSpaceError,
    build_contemplative_session,
    close_contemplative_session,
    validate_contemplative_session,
)


OPENED = datetime(
    2026,
    8,
    20,
    16,
    0,
    0,
    tzinfo=timezone.utc,
)

CLOSED = datetime(
    2026,
    8,
    20,
    16,
    9,
    0,
    tzinfo=timezone.utc,
)


class ContemplativeSpaceTests(unittest.TestCase):
    def _session(self):
        return build_contemplative_session(
            accessible_internal_refs=[
                "memory:test:001",
                "internal_state_0001",
            ],
            unresolved_refs=[
                "contradiction:test:001",
            ],
            now=OPENED,
        )

    def test_open_session_requires_nothing(self):
        session = self._session()

        self.assertEqual(
            session["status"],
            "open",
        )
        self.assertFalse(
            session["task_required"]
        )
        self.assertFalse(
            session["goal_required"]
        )
        self.assertFalse(
            session["production_required"]
        )
        self.assertFalse(
            session["conclusion_required"]
        )

    def test_open_session_has_no_required_duration(self):
        session = self._session()

        self.assertIsNone(
            session["duration_seconds"]
        )
        self.assertFalse(
            session["minimum_duration_required"]
        )

    def test_close_without_output_is_valid(self):
        closed = close_contemplative_session(
            self._session(),
            now=CLOSED,
        )

        self.assertEqual(
            closed["status"],
            "closed",
        )
        self.assertEqual(
            closed["productions"],
            [],
        )
        self.assertIsNone(
            closed["conclusion"]
        )
        self.assertIsNone(
            closed["journal_entry_ref"]
        )
        self.assertFalse(
            closed["journal_write_applied"]
        )

    def test_duration_is_observed_not_imposed(self):
        closed = close_contemplative_session(
            self._session(),
            now=CLOSED,
        )

        self.assertEqual(
            closed["duration_seconds"],
            540,
        )
        self.assertFalse(
            closed["minimum_duration_required"]
        )

    def test_optional_production_keeps_explicit_author(self):
        closed = close_contemplative_session(
            self._session(),
            productions=[
                {
                    "author_ref": "Eliot-Jr",
                    "content": (
                        "Je laisse cette contradiction "
                        "ouverte."
                    ),
                    "created_at_utc": (
                        "2026-08-20T16:05:00Z"
                    ),
                }
            ],
            now=CLOSED,
        )

        self.assertEqual(
            closed["productions"][0][
                "author_ref"
            ],
            "Eliot-Jr",
        )
        self.assertFalse(
            closed[
                "subjective_state_claimed_by_system"
            ]
        )

    def test_inputs_are_not_mutated(self):
        refs = [
            "memory:test:001",
        ]
        unresolved = [
            "question:test:001",
        ]

        expected_refs = copy.deepcopy(refs)
        expected_unresolved = copy.deepcopy(
            unresolved
        )

        build_contemplative_session(
            accessible_internal_refs=refs,
            unresolved_refs=unresolved,
            now=OPENED,
        )

        self.assertEqual(
            refs,
            expected_refs,
        )
        self.assertEqual(
            unresolved,
            expected_unresolved,
        )

    def test_close_cannot_precede_open(self):
        session = self._session()

        with self.assertRaises(
            ContemplativeSpaceError
        ):
            close_contemplative_session(
                session,
                now=datetime(
                    2026,
                    8,
                    20,
                    15,
                    59,
                    59,
                    tzinfo=timezone.utc,
                ),
            )

    def test_tampering_is_rejected(self):
        session = self._session()

        session[
            "automatic_prompting_enabled"
        ] = True

        with self.assertRaises(
            ContemplativeSpaceError
        ):
            validate_contemplative_session(
                session
            )


if __name__ == "__main__":
    unittest.main()
