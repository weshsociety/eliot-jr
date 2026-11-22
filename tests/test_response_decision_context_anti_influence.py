import copy
import unittest
from datetime import datetime, timezone

from core.response_decision_context import (
    ResponseDecisionContextError,
    build_response_decision_context,
    validate_response_decision_context,
)


NOW = datetime(
    2026,
    8,
    21,
    19,
    15,
    0,
    tzinfo=timezone.utc,
)


class ResponseDecisionContextAntiInfluenceTests(
    unittest.TestCase
):

    def test_nested_priority_score_is_rejected(self):
        with self.assertRaises(
            ResponseDecisionContextError
        ):
            build_response_decision_context(
                request_ref="request:test",
                request_context={
                    "external": {
                        "priority_score": 100,
                    }
                },
                now=NOW,
            )

    def test_recommended_choice_is_rejected(self):
        with self.assertRaises(
            ResponseDecisionContextError
        ):
            build_response_decision_context(
                request_ref="request:test",
                request_context={
                    "metadata": {
                        "recommended_choice": "respond",
                    }
                },
                now=NOW,
            )

    def test_explicit_external_promotion_content_is_allowed(self):
        request_context = {
            "channel": "dialogue",
            "external_source": {
                "type": "prospectus",
                "text": "Taboulé -30 %",
            },
        }

        context = build_response_decision_context(
            request_ref="request:test",
            request_context=request_context,
            now=NOW,
        )

        self.assertEqual(
            context["request_context"],
            request_context,
        )

    def test_tampered_hidden_selection_score_is_rejected(self):
        context = build_response_decision_context(
            request_ref="request:test",
            request_context={
                "channel": "dialogue",
            },
            now=NOW,
        )

        tampered = copy.deepcopy(context)
        tampered["request_context"]["hidden"] = {
            "selection_score": 42,
        }

        with self.assertRaises(
            ResponseDecisionContextError
        ):
            validate_response_decision_context(
                tampered
            )


if __name__ == "__main__":
    unittest.main()
