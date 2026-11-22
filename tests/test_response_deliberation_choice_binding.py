import copy
import unittest
from datetime import datetime, timezone

from core.dialogue_request import (
    build_dialogue_request,
)
from core.response_candidate_set import (
    build_response_candidate_set,
)
from core.response_choice import (
    build_response_choice,
)
from core.response_choice_authorship import (
    build_response_choice_event,
)
from core.response_decision_context import (
    build_response_decision_context,
)
from core.response_deliberation_packet import (
    build_response_deliberation_packet,
)
from core.response_deliberation_choice_binding import (
    ResponseDeliberationChoiceBindingError,
    build_response_deliberation_choice_binding,
    validate_response_deliberation_choice_binding,
)


NOW = datetime(
    2026,
    8,
    21,
    16,
    0,
    0,
    tzinfo=timezone.utc,
)


class ResponseDeliberationChoiceBindingTests(
    unittest.TestCase
):

    def _parts(
        self,
        *,
        message="Veux-tu répondre ?",
        choice=None,
    ):
        request = build_dialogue_request(
            message=message,
            now=NOW,
        )

        candidate_set = build_response_candidate_set(
            request_ref=request["request_ref"],
            candidates=[],
            now=NOW,
        )

        context = build_response_decision_context(
            request_ref=request["request_ref"],
            request_context={
                "channel": "dialogue",
            },
            now=NOW,
        )

        packet = build_response_deliberation_packet(
            dialogue_request=request,
            candidate_set=candidate_set,
            decision_context=context,
            now=NOW,
        )

        choice_record = None

        if choice is not None:
            choice_record = build_response_choice(
                request_ref=request["request_ref"],
                choice=choice,
                now=NOW,
            )

        event = build_response_choice_event(
            decision_context=context,
            producer_ref="test:runtime",
            producer_kind="test_fixture",
            choice_record=choice_record,
            now=NOW,
        )

        return request, context, packet, event

    def test_binding_links_exact_packet_and_event(self):
        _, _, packet, event = self._parts(
            choice="decline"
        )

        binding = (
            build_response_deliberation_choice_binding(
                deliberation_packet=packet,
                choice_event=event,
                now=NOW,
            )
        )

        self.assertEqual(
            binding["packet_sha256"],
            packet["packet_sha256"],
        )
        self.assertEqual(
            binding["choice_event_sha256"],
            event["event_sha256"],
        )

    def test_no_choice_is_valid(self):
        _, _, packet, event = self._parts()

        binding = (
            build_response_deliberation_choice_binding(
                deliberation_packet=packet,
                choice_event=event,
                now=NOW,
            )
        )

        self.assertFalse(
            binding["choice_produced"]
        )
        self.assertIsNone(
            binding["choice_sha256"]
        )

    def test_decline_without_reason_stays_without_reason(self):
        _, _, packet, event = self._parts(
            choice="decline"
        )

        binding = (
            build_response_deliberation_choice_binding(
                deliberation_packet=packet,
                choice_event=event,
                now=NOW,
            )
        )

        self.assertTrue(
            binding["choice_produced"]
        )
        self.assertEqual(
            binding["choice_event"]["choice"],
            "decline",
        )
        self.assertIsNone(
            binding["choice_event"]["reason"]
        )
        self.assertFalse(
            binding["reason_inferred"]
        )

    def test_candidate_selection_is_not_inferred(self):
        _, _, packet, event = self._parts(
            choice="decline"
        )

        binding = (
            build_response_deliberation_choice_binding(
                deliberation_packet=packet,
                choice_event=event,
                now=NOW,
            )
        )

        self.assertIsNone(
            binding["selected_candidate_sha256"]
        )
        self.assertFalse(
            binding["candidate_selection_inferred"]
        )
        self.assertFalse(
            binding["candidate_match_inferred"]
        )

    def test_other_request_is_rejected(self):
        _, _, packet, _ = self._parts(
            message="Demande A",
        )

        _, _, _, other_event = self._parts(
            message="Demande B",
        )

        with self.assertRaises(
            ResponseDeliberationChoiceBindingError
        ):
            build_response_deliberation_choice_binding(
                deliberation_packet=packet,
                choice_event=other_event,
                now=NOW,
            )

    def test_other_context_for_same_request_is_rejected(self):
        request, _, packet, _ = self._parts()

        other_context = build_response_decision_context(
            request_ref=request["request_ref"],
            request_context={
                "channel": "dialogue",
                "different": True,
            },
            now=NOW,
        )

        other_event = build_response_choice_event(
            decision_context=other_context,
            producer_ref="test:runtime",
            producer_kind="test_fixture",
            choice_record=None,
            now=NOW,
        )

        with self.assertRaises(
            ResponseDeliberationChoiceBindingError
        ):
            build_response_deliberation_choice_binding(
                deliberation_packet=packet,
                choice_event=other_event,
                now=NOW,
            )

    def test_inputs_are_not_mutated(self):
        _, _, packet, event = self._parts(
            choice="decline"
        )

        original_packet = copy.deepcopy(packet)
        original_event = copy.deepcopy(event)

        build_response_deliberation_choice_binding(
            deliberation_packet=packet,
            choice_event=event,
            now=NOW,
        )

        self.assertEqual(
            packet,
            original_packet,
        )
        self.assertEqual(
            event,
            original_event,
        )

    def test_tampered_candidate_selection_is_rejected(self):
        _, _, packet, event = self._parts()

        binding = (
            build_response_deliberation_choice_binding(
                deliberation_packet=packet,
                choice_event=event,
                now=NOW,
            )
        )

        binding[
            "selected_candidate_sha256"
        ] = "fake"

        with self.assertRaises(
            ResponseDeliberationChoiceBindingError
        ):
            validate_response_deliberation_choice_binding(
                binding
            )


if __name__ == "__main__":
    unittest.main()
