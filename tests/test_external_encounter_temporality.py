import copy
import unittest

from core.external_encounter_temporality import (
    EncounterTemporalityError,
    record_revisit,
)


class ExternalEncounterTemporalityTests(
    unittest.TestCase
):
    SHA = "a" * 64
    NOW = "2026-09-23T10:30:00+00:00"

    def test_first_revisit_is_appended(self):
        state = {
            "revisit_count": 0,
            "revisits": [],
        }

        result = record_revisit(
            state,
            revisited_at_utc=self.NOW,
            source_sha256=self.SHA,
        )

        self.assertEqual(
            result["revisit_count"],
            1,
        )

        self.assertEqual(
            len(result["revisits"]),
            1,
        )

        self.assertEqual(
            result["revisits"][0],
            {
                "revisited_at_utc": self.NOW,
                "source_sha256": self.SHA,
                "epistemic_change": False,
            },
        )

    def test_input_is_not_mutated(self):
        state = {
            "revisit_count": 0,
            "revisits": [],
        }

        original = copy.deepcopy(state)

        record_revisit(
            state,
            revisited_at_utc=self.NOW,
            source_sha256=self.SHA,
        )

        self.assertEqual(
            state,
            original,
        )

    def test_existing_history_is_preserved(self):
        first = {
            "revisited_at_utc":
                "2026-09-22T10:00:00+00:00",
            "source_sha256": self.SHA,
            "epistemic_change": False,
        }

        state = {
            "revisit_count": 1,
            "revisits": [first],
        }

        result = record_revisit(
            state,
            revisited_at_utc=self.NOW,
            source_sha256=self.SHA,
        )

        self.assertEqual(
            result["revisit_count"],
            2,
        )

        self.assertEqual(
            result["revisits"][0],
            first,
        )

        self.assertEqual(
            result["revisits"][1][
                "epistemic_change"
            ],
            False,
        )

    def test_incoherent_history_is_rejected(self):
        state = {
            "revisit_count": 2,
            "revisits": [],
        }

        with self.assertRaises(
            EncounterTemporalityError
        ):
            record_revisit(
                state,
                revisited_at_utc=self.NOW,
                source_sha256=self.SHA,
            )

    def test_timestamp_requires_timezone(self):
        state = {
            "revisit_count": 0,
            "revisits": [],
        }

        with self.assertRaises(
            EncounterTemporalityError
        ):
            record_revisit(
                state,
                revisited_at_utc=(
                    "2026-09-23T10:30:00"
                ),
                source_sha256=self.SHA,
            )


if __name__ == "__main__":
    unittest.main()
