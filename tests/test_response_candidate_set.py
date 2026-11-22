import copy
import unittest
from datetime import datetime, timezone

from core.response_candidate import (
    build_response_candidate,
)
from core.response_candidate_set import (
    ResponseCandidateSetError,
    build_response_candidate_set,
    validate_response_candidate_set,
)


NOW = datetime(
    2026,
    8,
    20,
    22,
    30,
    0,
    tzinfo=timezone.utc,
)


class ResponseCandidateSetTests(unittest.TestCase):

    def _candidate(
        self,
        producer_kind: str,
        producer_ref: str,
        content: str,
    ):
        return build_response_candidate(
            request_ref="request:test:001",
            producer_ref=producer_ref,
            producer_kind=producer_kind,
            content=content,
            now=NOW,
        )

    def test_empty_candidate_set_is_valid(self):
        candidate_set = build_response_candidate_set(
            request_ref="request:test:001",
            candidates=[],
            now=NOW,
        )

        self.assertEqual(
            candidate_set["candidate_count"],
            0,
        )
        self.assertEqual(
            candidate_set["candidates_by_sha256"],
            {},
        )
        self.assertFalse(
            candidate_set["selection_required"]
        )

    def test_multiple_candidates_have_no_winner(self):
        first = self._candidate(
            "faculty",
            "faculty:orientation",
            "Possibilité faculty.",
        )
        second = self._candidate(
            "will",
            "will:orientation",
            "Possibilité will.",
        )

        candidate_set = build_response_candidate_set(
            request_ref="request:test:001",
            candidates=[first, second],
            now=NOW,
        )

        self.assertEqual(
            candidate_set["candidate_count"],
            2,
        )
        self.assertIsNone(
            candidate_set["selected_candidate_sha256"]
        )
        self.assertIsNone(
            candidate_set["default_candidate_sha256"]
        )

    def test_input_order_has_no_semantic_effect(self):
        first = self._candidate(
            "faculty",
            "faculty:orientation",
            "Possibilité faculty.",
        )
        second = self._candidate(
            "will",
            "will:orientation",
            "Possibilité will.",
        )

        set_ab = build_response_candidate_set(
            request_ref="request:test:001",
            candidates=[first, second],
            now=NOW,
        )

        set_ba = build_response_candidate_set(
            request_ref="request:test:001",
            candidates=[second, first],
            now=NOW,
        )

        self.assertEqual(set_ab, set_ba)
        self.assertEqual(
            set_ab["candidate_set_sha256"],
            set_ba["candidate_set_sha256"],
        )

    def test_no_ranking_scoring_or_position_priority(self):
        candidate_set = build_response_candidate_set(
            request_ref="request:test:001",
            candidates=[],
            now=NOW,
        )

        self.assertEqual(
            candidate_set["ordering_semantics"],
            "none",
        )
        self.assertFalse(
            candidate_set["ranking_enabled"]
        )
        self.assertFalse(
            candidate_set["scores_enabled"]
        )
        self.assertFalse(
            candidate_set["positional_priority_enabled"]
        )

    def test_duplicate_candidate_is_rejected(self):
        candidate = self._candidate(
            "retrieval",
            "retrieval:internal",
            "Possibilité retrieval.",
        )

        with self.assertRaises(
            ResponseCandidateSetError
        ):
            build_response_candidate_set(
                request_ref="request:test:001",
                candidates=[
                    candidate,
                    candidate,
                ],
                now=NOW,
            )

    def test_candidate_from_other_request_is_rejected(self):
        candidate = build_response_candidate(
            request_ref="request:test:OTHER",
            producer_ref="retrieval:internal",
            producer_kind="retrieval",
            content="Possibilité.",
            now=NOW,
        )

        with self.assertRaises(
            ResponseCandidateSetError
        ):
            build_response_candidate_set(
                request_ref="request:test:001",
                candidates=[candidate],
                now=NOW,
            )

    def test_inputs_are_not_mutated(self):
        candidate = self._candidate(
            "desire",
            "desire:orientation",
            "Possibilité desire.",
        )

        candidates = [candidate]
        original = copy.deepcopy(candidates)

        build_response_candidate_set(
            request_ref="request:test:001",
            candidates=candidates,
            now=NOW,
        )

        self.assertEqual(
            candidates,
            original,
        )

    def test_hidden_default_candidate_is_rejected(self):
        candidate_set = build_response_candidate_set(
            request_ref="request:test:001",
            candidates=[],
            now=NOW,
        )

        candidate_set["default_candidate_sha256"] = "fake"

        with self.assertRaises(
            ResponseCandidateSetError
        ):
            validate_response_candidate_set(
                candidate_set
            )


if __name__ == "__main__":
    unittest.main()
