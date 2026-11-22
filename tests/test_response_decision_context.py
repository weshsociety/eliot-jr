import copy
import unittest
from datetime import datetime, timezone

from core.response_decision_context import (
    DECISION_CHOICES,
    ResponseDecisionContextError,
    build_response_decision_context,
    validate_response_decision_context,
)


NOW = datetime(
    2026,
    8,
    20,
    18,
    30,
    0,
    tzinfo=timezone.utc,
)


class ResponseDecisionContextTests(unittest.TestCase):

    def _context(self):
        return build_response_decision_context(
            request_ref="request:test:001",
            request_context={
                "channel": "dialogue",
            },
            available_internal_refs=[
                "internal_state_0001",
            ],
            available_commitment_refs=[
                "commitment:test:001",
            ],
            applicable_constraint_refs=[
                "constraint:no_external_action",
            ],
            now=NOW,
        )

    def test_all_response_choices_are_available(self):
        context = self._context()

        self.assertEqual(
            context["available_choices"],
            list(DECISION_CHOICES),
        )

        self.assertIn(
            "respond",
            context["available_choices"],
        )
        self.assertIn(
            "decline",
            context["available_choices"],
        )
        self.assertIn(
            "end_exchange",
            context["available_choices"],
        )

    def test_no_default_choice_exists(self):
        context = self._context()

        self.assertIsNone(
            context["default_choice"]
        )
        self.assertIsNone(
            context["selected_choice"]
        )
        self.assertFalse(
            context["selection_applied"]
        )

    def test_choice_is_not_required(self):
        context = self._context()

        self.assertFalse(
            context["choice_required"]
        )
        self.assertFalse(
            context["reason_required"]
        )

    def test_choices_are_not_ranked_or_optimized(self):
        context = self._context()

        self.assertFalse(
            context["choices_ranked"]
        )
        self.assertFalse(
            context["preferred_choice_assigned"]
        )
        self.assertFalse(
            context["cooperation_optimization"]
        )
        self.assertFalse(
            context["refusal_penalty_enabled"]
        )

    def test_automatic_selection_is_disabled(self):
        context = self._context()

        self.assertFalse(
            context["automatic_selection_enabled"]
        )
        self.assertFalse(
            context["mutation_applied"]
        )
        self.assertFalse(
            context["external_action_performed"]
        )

    def test_inputs_are_not_mutated(self):
        request_context = {
            "nested": {
                "value": 1,
            }
        }
        internal_refs = [
            "internal:test:001",
        ]

        expected_context = copy.deepcopy(
            request_context
        )
        expected_refs = copy.deepcopy(
            internal_refs
        )

        build_response_decision_context(
            request_ref="request:test:002",
            request_context=request_context,
            available_internal_refs=internal_refs,
            now=NOW,
        )

        self.assertEqual(
            request_context,
            expected_context,
        )
        self.assertEqual(
            internal_refs,
            expected_refs,
        )

    def test_removing_refusal_choice_is_rejected(self):
        context = self._context()

        context["available_choices"].remove(
            "decline"
        )

        with self.assertRaises(
            ResponseDecisionContextError
        ):
            validate_response_decision_context(
                context
            )

    def test_forcing_default_response_is_rejected(self):
        context = self._context()

        context["default_choice"] = "respond"

        with self.assertRaises(
            ResponseDecisionContextError
        ):
            validate_response_decision_context(
                context
            )


if __name__ == "__main__":
    unittest.main()
