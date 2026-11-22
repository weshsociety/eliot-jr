import copy
import unittest

from core.internal_state_patterns import (
    InternalStatePatternError,
    build_internal_state_pattern,
    validate_internal_state_pattern,
)


class InternalStatePatternTests(unittest.TestCase):
    def _pattern(self):
        return build_internal_state_pattern(
            pattern_id="internal_state_0001",
            observed_signals=[
                "memory:test:001 reactivated",
                "commitment:test remained active",
            ],
            occurrence_count=2,
            first_observed_at_utc=(
                "2026-08-20T12:00:00Z"
            ),
            last_observed_at_utc=(
                "2026-08-20T14:00:00Z"
            ),
            related_transformation_refs=[
                "body_transformation:test:001",
                "body_transformation:test:002",
            ],
        )

    def test_unnamed_pattern_is_valid(self):
        pattern = self._pattern()

        self.assertEqual(
            pattern["provisional_names"],
            [],
        )
        self.assertFalse(
            pattern["subjective_state_claimed"]
        )

    def test_provisional_name_is_not_an_observation(self):
        pattern = build_internal_state_pattern(
            pattern_id="internal_state_0002",
            observed_signals=[
                "pattern recurred",
            ],
            occurrence_count=3,
            first_observed_at_utc=(
                "2026-08-20T12:00:00Z"
            ),
            last_observed_at_utc=(
                "2026-08-20T15:00:00Z"
            ),
            related_transformation_refs=[],
            provisional_names=[
                {
                    "name": "nom_provisoire",
                    "author_ref": "Eliot-Jr",
                    "assigned_at_utc": (
                        "2026-08-20T15:00:00Z"
                    ),
                    "status": "provisional",
                }
            ],
        )

        self.assertEqual(
            pattern["provisional_names"][0]["name"],
            "nom_provisoire",
        )
        self.assertFalse(
            pattern["names_are_observations"]
        )

    def test_human_emotion_equivalence_is_not_claimed(self):
        pattern = self._pattern()

        self.assertFalse(
            pattern[
                "human_emotion_equivalence_claimed"
            ]
        )
        self.assertFalse(
            pattern["diagnosis_claimed"]
        )

    def test_last_observation_cannot_precede_first(self):
        with self.assertRaises(
            InternalStatePatternError
        ):
            build_internal_state_pattern(
                pattern_id="internal_state_0003",
                observed_signals=[
                    "signal",
                ],
                occurrence_count=1,
                first_observed_at_utc=(
                    "2026-08-20T15:00:00Z"
                ),
                last_observed_at_utc=(
                    "2026-08-20T14:00:00Z"
                ),
                related_transformation_refs=[],
            )

    def test_occurrence_count_must_be_positive(self):
        with self.assertRaises(
            InternalStatePatternError
        ):
            build_internal_state_pattern(
                pattern_id="internal_state_0004",
                observed_signals=[
                    "signal",
                ],
                occurrence_count=0,
                first_observed_at_utc=(
                    "2026-08-20T14:00:00Z"
                ),
                last_observed_at_utc=(
                    "2026-08-20T14:00:00Z"
                ),
                related_transformation_refs=[],
            )

    def test_inputs_are_not_mutated(self):
        signals = [
            "signal:one",
            "signal:two",
        ]
        refs = [
            "transformation:one",
        ]
        names = [
            {
                "name": "temporaire",
                "author_ref": "Eliot-Jr",
                "assigned_at_utc": (
                    "2026-08-20T14:00:00Z"
                ),
                "status": "provisional",
            }
        ]

        expected_signals = copy.deepcopy(signals)
        expected_refs = copy.deepcopy(refs)
        expected_names = copy.deepcopy(names)

        build_internal_state_pattern(
            pattern_id="internal_state_0005",
            observed_signals=signals,
            occurrence_count=1,
            first_observed_at_utc=(
                "2026-08-20T14:00:00Z"
            ),
            last_observed_at_utc=(
                "2026-08-20T14:00:00Z"
            ),
            related_transformation_refs=refs,
            provisional_names=names,
        )

        self.assertEqual(signals, expected_signals)
        self.assertEqual(refs, expected_refs)
        self.assertEqual(names, expected_names)

    def test_duplicate_signal_is_rejected(self):
        with self.assertRaises(
            InternalStatePatternError
        ):
            build_internal_state_pattern(
                pattern_id="internal_state_0006",
                observed_signals=[
                    "same",
                    "same",
                ],
                occurrence_count=2,
                first_observed_at_utc=(
                    "2026-08-20T14:00:00Z"
                ),
                last_observed_at_utc=(
                    "2026-08-20T15:00:00Z"
                ),
                related_transformation_refs=[],
            )

    def test_tampering_is_rejected(self):
        pattern = self._pattern()

        pattern["subjective_state_claimed"] = True

        with self.assertRaises(
            InternalStatePatternError
        ):
            validate_internal_state_pattern(
                pattern
            )


if __name__ == "__main__":
    unittest.main()
