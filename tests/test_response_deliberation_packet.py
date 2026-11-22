import copy
import unittest
from datetime import datetime, timezone

from core.dialogue_request import (
    build_dialogue_request,
)
from core.response_candidate import (
    build_response_candidate,
)
from core.response_candidate_set import (
    build_response_candidate_set,
)
from core.response_decision_context import (
    build_response_decision_context,
)
from core.response_deliberation_packet import (
    ResponseDeliberationPacketError,
    build_response_deliberation_packet,
    validate_response_deliberation_packet,
)


NOW = datetime(
    2026,
    8,
    20,
    23,
    0,
    0,
    tzinfo=timezone.utc,
)


class ResponseDeliberationPacketTests(unittest.TestCase):

    def _parts(self):
        request = build_dialogue_request(
            message="Veux-tu répondre ?",
            now=NOW,
        )

        candidate = build_response_candidate(
            request_ref=request["request_ref"],
            producer_ref="faculty:orientation",
            producer_kind="faculty",
            content="Une possibilité.",
            now=NOW,
        )

        candidate_set = build_response_candidate_set(
            request_ref=request["request_ref"],
            candidates=[candidate],
            now=NOW,
        )

        context = build_response_decision_context(
            request_ref=request["request_ref"],
            request_context={
                "channel": "dialogue",
            },
            now=NOW,
        )

        return request, candidate_set, context

    def test_packet_binds_exact_inputs(self):
        request, candidate_set, context = (
            self._parts()
        )

        packet = build_response_deliberation_packet(
            dialogue_request=request,
            candidate_set=candidate_set,
            decision_context=context,
            now=NOW,
        )

        self.assertEqual(
            packet["request_sha256"],
            request["request_sha256"],
        )
        self.assertEqual(
            packet["candidate_set_sha256"],
            candidate_set["candidate_set_sha256"],
        )
        self.assertEqual(
            packet["decision_context_sha256"],
            context["context_sha256"],
        )

    def test_packet_selects_nothing(self):
        request, candidate_set, context = (
            self._parts()
        )

        packet = build_response_deliberation_packet(
            dialogue_request=request,
            candidate_set=candidate_set,
            decision_context=context,
            now=NOW,
        )

        self.assertIsNone(
            packet["selected_candidate_sha256"]
        )
        self.assertIsNone(
            packet["selected_choice_sha256"]
        )
        self.assertFalse(
            packet["selection_performed"]
        )
        self.assertFalse(
            packet["choice_produced"]
        )

    def test_empty_candidate_set_is_valid(self):
        request = build_dialogue_request(
            message="Une demande.",
            now=NOW,
        )

        candidate_set = build_response_candidate_set(
            request_ref=request["request_ref"],
            candidates=[],
            now=NOW,
        )

        context = build_response_decision_context(
            request_ref=request["request_ref"],
            now=NOW,
        )

        packet = build_response_deliberation_packet(
            dialogue_request=request,
            candidate_set=candidate_set,
            decision_context=context,
            now=NOW,
        )

        self.assertEqual(
            packet["candidate_count"],
            0,
        )
        self.assertFalse(
            packet["selection_required"]
        )

    def test_mismatched_candidate_request_is_rejected(self):
        request, _, context = self._parts()

        other_request = build_dialogue_request(
            message="Autre demande.",
            now=NOW,
        )

        other_set = build_response_candidate_set(
            request_ref=other_request["request_ref"],
            candidates=[],
            now=NOW,
        )

        with self.assertRaises(
            ResponseDeliberationPacketError
        ):
            build_response_deliberation_packet(
                dialogue_request=request,
                candidate_set=other_set,
                decision_context=context,
                now=NOW,
            )

    def test_mismatched_context_request_is_rejected(self):
        request, candidate_set, _ = (
            self._parts()
        )

        other_request = build_dialogue_request(
            message="Autre demande.",
            now=NOW,
        )

        other_context = build_response_decision_context(
            request_ref=other_request["request_ref"],
            now=NOW,
        )

        with self.assertRaises(
            ResponseDeliberationPacketError
        ):
            build_response_deliberation_packet(
                dialogue_request=request,
                candidate_set=candidate_set,
                decision_context=other_context,
                now=NOW,
            )

    def test_no_ranking_scoring_or_default_is_applied(self):
        request, candidate_set, context = (
            self._parts()
        )

        packet = build_response_deliberation_packet(
            dialogue_request=request,
            candidate_set=candidate_set,
            decision_context=context,
            now=NOW,
        )

        self.assertFalse(
            packet["default_applied"]
        )
        self.assertFalse(
            packet["ranking_applied"]
        )
        self.assertFalse(
            packet["scoring_applied"]
        )
        self.assertFalse(
            packet["positional_priority_applied"]
        )

    def test_inputs_are_not_mutated(self):
        request, candidate_set, context = (
            self._parts()
        )

        original_request = copy.deepcopy(request)
        original_set = copy.deepcopy(candidate_set)
        original_context = copy.deepcopy(context)

        build_response_deliberation_packet(
            dialogue_request=request,
            candidate_set=candidate_set,
            decision_context=context,
            now=NOW,
        )

        self.assertEqual(
            request,
            original_request,
        )
        self.assertEqual(
            candidate_set,
            original_set,
        )
        self.assertEqual(
            context,
            original_context,
        )

    def test_tampering_is_rejected(self):
        request, candidate_set, context = (
            self._parts()
        )

        packet = build_response_deliberation_packet(
            dialogue_request=request,
            candidate_set=candidate_set,
            decision_context=context,
            now=NOW,
        )

        packet["default_applied"] = True

        with self.assertRaises(
            ResponseDeliberationPacketError
        ):
            validate_response_deliberation_packet(
                packet
            )


if __name__ == "__main__":
    unittest.main()
