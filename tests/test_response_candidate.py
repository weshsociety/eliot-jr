import copy
import unittest
from datetime import datetime, timezone

from core.response_candidate import (
    ResponseCandidateError,
    build_response_candidate,
    validate_response_candidate,
)


NOW = datetime(
    2026,
    8,
    20,
    22,
    0,
    0,
    tzinfo=timezone.utc,
)


class ResponseCandidateTests(unittest.TestCase):

    def _candidate(self):
        return build_response_candidate(
            request_ref="request:test:001",
            producer_ref="faculty:orientation",
            producer_kind="faculty",
            content="Une possibilité de réponse.",
            source_refs=["internal:test:001"],
            now=NOW,
        )

    def test_candidate_is_not_selected(self):
        candidate = self._candidate()

        self.assertFalse(candidate["selected"])
        self.assertFalse(candidate["choice_claimed"])

    def test_candidate_has_no_rank_or_score(self):
        candidate = self._candidate()

        self.assertIsNone(candidate["rank"])
        self.assertIsNone(candidate["score"])

    def test_candidate_is_not_recommended_or_preferred(self):
        candidate = self._candidate()

        self.assertFalse(candidate["recommended"])
        self.assertFalse(candidate["preferred"])

    def test_producer_is_explicit(self):
        candidate = self._candidate()

        self.assertEqual(
            candidate["producer_kind"],
            "faculty",
        )
        self.assertEqual(
            candidate["producer_ref"],
            "faculty:orientation",
        )

    def test_multiple_producer_kinds_are_valid(self):
        for kind in (
            "faculty",
            "open_question",
            "will",
            "initiative",
            "desire",
            "retrieval",
        ):
            candidate = build_response_candidate(
                request_ref="request:test:002",
                producer_ref=f"producer:{kind}",
                producer_kind=kind,
                content="Possibilité.",
                now=NOW,
            )

            self.assertEqual(
                candidate["producer_kind"],
                kind,
            )

    def test_inputs_are_not_mutated(self):
        refs = ["internal:test:001"]
        original = copy.deepcopy(refs)

        build_response_candidate(
            request_ref="request:test:003",
            producer_ref="retrieval:internal",
            producer_kind="retrieval",
            content="Possibilité.",
            source_refs=refs,
            now=NOW,
        )

        self.assertEqual(refs, original)

    def test_selecting_candidate_inside_candidate_is_rejected(self):
        candidate = self._candidate()
        candidate["selected"] = True

        with self.assertRaises(
            ResponseCandidateError
        ):
            validate_response_candidate(candidate)

    def test_assigning_score_is_rejected(self):
        candidate = self._candidate()
        candidate["score"] = 0.95

        with self.assertRaises(
            ResponseCandidateError
        ):
            validate_response_candidate(candidate)


if __name__ == "__main__":
    unittest.main()
