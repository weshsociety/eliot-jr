import copy
import unittest
from datetime import datetime, timezone

from core.dialogue_request import build_dialogue_request
from core.response_candidate_set import (
    build_response_candidate_set,
)
from core.response_choice import build_response_choice
from core.response_choice_producer import (
    ResponseChoiceProductionError,
    produce_response_choice_preview,
)
from core.response_decision_context import (
    build_response_decision_context,
)
from core.response_deliberation_packet import (
    build_response_deliberation_packet,
)


NOW = datetime(
    2026,
    8,
    21,
    17,
    30,
    0,
    tzinfo=timezone.utc,
)


class ResponseChoiceProducerTests(unittest.TestCase):

    def _packet(self, message="Veux-tu répondre ?"):
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

        return request, packet

    def test_none_is_valid_and_stays_none(self):
        _, packet = self._packet()

        result = produce_response_choice_preview(
            deliberation_packet=packet,
            producer=lambda _packet: None,
        )

        self.assertIsNone(result)

    def test_decline_without_reason_is_preserved(self):
        request, packet = self._packet()

        def producer(_packet):
            return build_response_choice(
                request_ref=request["request_ref"],
                choice="decline",
                reason=None,
                now=NOW,
            )

        result = produce_response_choice_preview(
            deliberation_packet=packet,
            producer=producer,
        )

        self.assertEqual(result["choice"], "decline")
        self.assertIsNone(result["reason"])

    def test_respond_with_content_is_valid(self):
        request, packet = self._packet()

        def producer(_packet):
            return build_response_choice(
                request_ref=request["request_ref"],
                choice="respond",
                response_content="Je réponds.",
                now=NOW,
            )

        result = produce_response_choice_preview(
            deliberation_packet=packet,
            producer=producer,
        )

        self.assertEqual(result["choice"], "respond")
        self.assertEqual(
            result["response_content"],
            "Je réponds.",
        )

    def test_non_mapping_output_is_rejected(self):
        _, packet = self._packet()

        with self.assertRaises(
            ResponseChoiceProductionError
        ):
            produce_response_choice_preview(
                deliberation_packet=packet,
                producer=lambda _packet: "respond",
            )

    def test_invalid_choice_is_rejected_not_repaired(self):
        _, packet = self._packet()

        with self.assertRaises(
            ResponseChoiceProductionError
        ):
            produce_response_choice_preview(
                deliberation_packet=packet,
                producer=lambda _packet: {
                    "choice": "respond",
                },
            )

    def test_other_request_choice_is_rejected(self):
        _, packet = self._packet(
            message="Demande A"
        )

        other_request = build_dialogue_request(
            message="Demande B",
            now=NOW,
        )

        def producer(_packet):
            return build_response_choice(
                request_ref=other_request[
                    "request_ref"
                ],
                choice="decline",
                now=NOW,
            )

        with self.assertRaises(
            ResponseChoiceProductionError
        ):
            produce_response_choice_preview(
                deliberation_packet=packet,
                producer=producer,
            )

    def test_producer_exception_is_not_fallback_to_respond(self):
        _, packet = self._packet()

        def producer(_packet):
            raise RuntimeError("boom")

        with self.assertRaises(
            ResponseChoiceProductionError
        ):
            produce_response_choice_preview(
                deliberation_packet=packet,
                producer=producer,
            )

    def test_producer_cannot_mutate_original_packet(self):
        _, packet = self._packet()
        original = copy.deepcopy(packet)

        def producer(received_packet):
            received_packet[
                "selection_performed"
            ] = True
            return None

        result = produce_response_choice_preview(
            deliberation_packet=packet,
            producer=producer,
        )

        self.assertIsNone(result)
        self.assertEqual(packet, original)

    def test_returned_choice_is_detached_from_producer_object(self):
        request, packet = self._packet()

        produced = build_response_choice(
            request_ref=request["request_ref"],
            choice="decline",
            now=NOW,
        )

        result = produce_response_choice_preview(
            deliberation_packet=packet,
            producer=lambda _packet: produced,
        )

        produced["choice"] = "respond"

        self.assertEqual(result["choice"], "decline")

    def test_producer_is_called_once_with_exact_packet_identity(self):
        _, packet = self._packet()
        observed = []

        def producer(received_packet):
            observed.append(
                received_packet["packet_sha256"]
            )
            return None

        produce_response_choice_preview(
            deliberation_packet=packet,
            producer=producer,
        )

        self.assertEqual(
            observed,
            [packet["packet_sha256"]],
        )


if __name__ == "__main__":
    unittest.main()
