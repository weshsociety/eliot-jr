import copy
import unittest
from datetime import datetime, timezone

from core.body_schema import (
    BodySchemaError,
    build_body_snapshot,
    build_body_transformation,
    validate_body_snapshot,
    validate_body_transformation,
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


class BodySchemaTests(unittest.TestCase):
    def _snapshot(
        self,
        active_memory: str,
    ):
        return build_body_snapshot(
            functional_state={
                "active_memory": active_memory,
                "active_commitment": "commitment_001",
            },
            component_refs={
                "memory": "memory_state:test",
                "will": "will_state:test",
            },
            now=NOW,
        )

    def test_snapshot_is_deterministic(self):
        first = self._snapshot("memory_001")
        second = self._snapshot("memory_001")

        self.assertEqual(first, second)
        self.assertFalse(
            first["subjective_state_claimed"]
        )
        self.assertFalse(
            first["interpretation_applied"]
        )

    def test_snapshot_does_not_mutate_inputs(self):
        state = {
            "active_memory": "memory_001",
            "nested": {"value": 1},
        }
        refs = {
            "memory": "memory_state:test",
        }

        expected_state = copy.deepcopy(state)
        expected_refs = copy.deepcopy(refs)

        build_body_snapshot(
            state,
            refs,
            now=NOW,
        )

        self.assertEqual(state, expected_state)
        self.assertEqual(refs, expected_refs)

    def test_tampered_snapshot_is_rejected(self):
        snapshot = self._snapshot("memory_001")
        snapshot["functional_state"][
            "active_memory"
        ] = "memory_tampered"

        with self.assertRaises(BodySchemaError):
            validate_body_snapshot(snapshot)

    def test_transformation_separates_observation_from_interpretation(self):
        before = self._snapshot("memory_001")
        after = self._snapshot("memory_002")

        transformation = build_body_transformation(
            event_ref="interaction:test:001",
            state_before=before,
            state_after=after,
            observed_changes=[
                "active_memory changed",
            ],
            persistent_changes=[],
            reactivated_memories=[
                "memory_002",
            ],
            affected_patterns=[],
            interpretations=[
                {
                    "author": "Eliot-Jr",
                    "statement": (
                        "Cette transformation pourrait "
                        "avoir une signification pour moi."
                    ),
                    "status": "provisional",
                }
            ],
            now=NOW,
        )

        self.assertEqual(
            transformation["observed_changes"],
            ["active_memory changed"],
        )
        self.assertEqual(
            len(transformation["interpretations"]),
            1,
        )
        self.assertFalse(
            transformation[
                "interpretations_are_observations"
            ]
        )
        self.assertFalse(
            transformation[
                "subjective_state_claimed"
            ]
        )

    def test_transformation_accepts_no_interpretation(self):
        transformation = build_body_transformation(
            event_ref="interaction:test:002",
            state_before=self._snapshot(
                "memory_001"
            ),
            state_after=self._snapshot(
                "memory_001"
            ),
            observed_changes=[],
            persistent_changes=[],
            reactivated_memories=[],
            affected_patterns=[],
            now=NOW,
        )

        self.assertEqual(
            transformation["interpretations"],
            [],
        )
        self.assertFalse(
            transformation["mutation_applied"]
        )
        self.assertFalse(
            transformation[
                "external_action_performed"
            ]
        )

    def test_invalid_observation_list_is_rejected(self):
        with self.assertRaises(BodySchemaError):
            build_body_transformation(
                event_ref="interaction:test:003",
                state_before=self._snapshot(
                    "memory_001"
                ),
                state_after=self._snapshot(
                    "memory_002"
                ),
                observed_changes=[
                    "valid",
                    42,
                ],
                persistent_changes=[],
                reactivated_memories=[],
                affected_patterns=[],
                now=NOW,
            )

    def test_tampered_transformation_is_rejected(self):
        transformation = build_body_transformation(
            event_ref="interaction:test:004",
            state_before=self._snapshot(
                "memory_001"
            ),
            state_after=self._snapshot(
                "memory_002"
            ),
            observed_changes=[
                "active_memory changed",
            ],
            persistent_changes=[],
            reactivated_memories=[],
            affected_patterns=[],
            now=NOW,
        )

        transformation["event_ref"] = (
            "interaction:tampered"
        )

        with self.assertRaises(BodySchemaError):
            validate_body_transformation(
                transformation
            )


if __name__ == "__main__":
    unittest.main()
