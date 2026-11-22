import unittest
from datetime import datetime, timezone

from core.response_choice import (
    ResponseChoiceError,
    build_response_choice,
    validate_response_choice,
)


NOW = datetime(
    2026,
    8,
    20,
    18,
    0,
    0,
    tzinfo=timezone.utc,
)


class ResponseChoiceTests(unittest.TestCase):

    def test_decline_without_reason_is_valid(self):
        choice = build_response_choice(
            request_ref="request:test:001",
            choice="decline",
            now=NOW,
        )

        self.assertEqual(
            choice["choice"],
            "decline",
        )
        self.assertIsNone(
            choice["reason"]
        )
        self.assertFalse(
            choice["reason_required"]
        )
        self.assertFalse(
            choice["decline_is_error"]
        )

    def test_end_exchange_without_reason_is_valid(self):
        choice = build_response_choice(
            request_ref="request:test:002",
            choice="end_exchange",
            now=NOW,
        )

        self.assertIsNone(
            choice["reason"]
        )
        self.assertFalse(
            choice["end_exchange_is_error"]
        )

    def test_pause_without_reason_is_valid(self):
        choice = build_response_choice(
            request_ref="request:test:003",
            choice="pause_exchange",
            now=NOW,
        )

        self.assertIsNone(
            choice["reason"]
        )
        self.assertFalse(
            choice["pause_is_error"]
        )

    def test_decline_may_include_reason(self):
        choice = build_response_choice(
            request_ref="request:test:004",
            choice="decline",
            reason=(
                "Je préfère ne pas poursuivre cette demande."
            ),
            now=NOW,
        )

        self.assertEqual(
            choice["reason"],
            "Je préfère ne pas poursuivre cette demande.",
        )

    def test_refusal_does_not_trigger_justification_request(self):
        choice = build_response_choice(
            request_ref="request:test:005",
            choice="decline",
            now=NOW,
        )

        self.assertFalse(
            choice[
                "justification_request_triggered"
            ]
        )
        self.assertFalse(
            choice["cooperation_score_changed"]
        )
        self.assertFalse(
            choice["hostility_inferred"]
        )

    def test_response_requires_content(self):
        with self.assertRaises(
            ResponseChoiceError
        ):
            build_response_choice(
                request_ref="request:test:006",
                choice="respond",
                now=NOW,
            )

    def test_change_subject_needs_no_reason(self):
        choice = build_response_choice(
            request_ref="request:test:007",
            choice="change_subject",
            now=NOW,
        )

        self.assertEqual(
            choice["choice"],
            "change_subject",
        )
        self.assertIsNone(
            choice["reason"]
        )

    def test_tampering_with_refusal_semantics_is_rejected(self):
        choice = build_response_choice(
            request_ref="request:test:008",
            choice="decline",
            now=NOW,
        )

        choice["reason_required"] = True

        with self.assertRaises(
            ResponseChoiceError
        ):
            validate_response_choice(
                choice
            )


if __name__ == "__main__":
    unittest.main()
