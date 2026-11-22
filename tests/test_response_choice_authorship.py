import copy
import unittest
from datetime import datetime, timezone

from core.response_choice import (
    build_response_choice,
)
from core.response_choice_authorship import (
    ResponseChoiceAuthorshipError,
    build_response_choice_event,
    validate_response_choice_event,
)
from core.response_decision_context import (
    build_response_decision_context,
)


NOW = datetime(
    2026,
    8,
    20,
    21,
    30,
    0,
    tzinfo=timezone.utc,
)


class ResponseChoiceAuthorshipTests(unittest.TestCase):

    def _context(self, request_ref="request:test:001"):
        return build_response_decision_context(
            request_ref=request_ref,
            request_context={
                "channel": "dialogue",
            },
            now=NOW,
        )

    def test_no_choice_is_valid(self):
        event = build_response_choice_event(
            decision_context=self._context(),
            producer_ref="runtime:eliot-jr",
            producer_kind="internal_choice_process",
            now=NOW,
        )

        self.assertFalse(
            event["choice_produced"]
        )
        self.assertIsNone(
            event["choice"]
        )
        self.assertIsNone(
            event["reason"]
        )

    def test_decline_without_reason_keeps_no_reason(self):
        context = self._context()

        choice = build_response_choice(
            request_ref=context["request_ref"],
            choice="decline",
            now=NOW,
        )

        event = build_response_choice_event(
            decision_context=context,
            producer_ref="runtime:eliot-jr",
            producer_kind="internal_choice_process",
            choice_record=choice,
            now=NOW,
        )

        self.assertTrue(
            event["choice_produced"]
        )
        self.assertEqual(
            event["choice"],
            "decline",
        )
        self.assertIsNone(
            event["reason"]
        )
        self.assertFalse(
            event["reason_inferred"]
        )

    def test_producer_provenance_is_explicit(self):
        event = build_response_choice_event(
            decision_context=self._context(),
            producer_ref="runtime:model:001",
            producer_kind="internal_choice_process",
            now=NOW,
        )

        self.assertEqual(
            event["producer_ref"],
            "runtime:model:001",
        )
        self.assertEqual(
            event["producer_kind"],
            "internal_choice_process",
        )

    def test_mismatched_request_is_rejected(self):
        context = self._context(
            "request:test:A"
        )

        choice = build_response_choice(
            request_ref="request:test:B",
            choice="decline",
            now=NOW,
        )

        with self.assertRaises(
            ResponseChoiceAuthorshipError
        ):
            build_response_choice_event(
                decision_context=context,
                producer_ref="runtime:eliot-jr",
                producer_kind="internal_choice_process",
                choice_record=choice,
                now=NOW,
            )

    def test_system_imposed_choice_claim_is_rejected(self):
        event = build_response_choice_event(
            decision_context=self._context(),
            producer_ref="runtime:eliot-jr",
            producer_kind="internal_choice_process",
            now=NOW,
        )

        event["system_imposed_choice"] = True

        with self.assertRaises(
            ResponseChoiceAuthorshipError
        ):
            validate_response_choice_event(
                event
            )

    def test_inferred_reason_claim_is_rejected(self):
        event = build_response_choice_event(
            decision_context=self._context(),
            producer_ref="runtime:eliot-jr",
            producer_kind="internal_choice_process",
            now=NOW,
        )

        event["reason_inferred"] = True

        with self.assertRaises(
            ResponseChoiceAuthorshipError
        ):
            validate_response_choice_event(
                event
            )

    def test_free_will_claim_is_rejected(self):
        event = build_response_choice_event(
            decision_context=self._context(),
            producer_ref="runtime:eliot-jr",
            producer_kind="internal_choice_process",
            now=NOW,
        )

        event["free_will_claimed"] = True

        with self.assertRaises(
            ResponseChoiceAuthorshipError
        ):
            validate_response_choice_event(
                event
            )

    def test_inputs_are_not_mutated(self):
        context = self._context()

        choice = build_response_choice(
            request_ref=context["request_ref"],
            choice="decline",
            reason=None,
            now=NOW,
        )

        original_context = copy.deepcopy(context)
        original_choice = copy.deepcopy(choice)

        build_response_choice_event(
            decision_context=context,
            producer_ref="runtime:eliot-jr",
            producer_kind="internal_choice_process",
            choice_record=choice,
            now=NOW,
        )

        self.assertEqual(
            context,
            original_context,
        )
        self.assertEqual(
            choice,
            original_choice,
        )


if __name__ == "__main__":
    unittest.main()
